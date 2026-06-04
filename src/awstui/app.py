from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version as _pkg_version

import boto3
import pyperclip
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane
from textual import work
from textual.worker import Worker, get_current_worker

from awstui.models import ContentPreview, ResourceDetails, TreeNode
from awstui.plugin import PluginRegistry
from awstui.services import discover_plugins
from awstui.widgets.detail_pane import DetailPane
from awstui.widgets.filter_dialog import FilterDialog
from awstui.widgets.nav_tree import AWSNavTree, NodeError, NodeSelected
from awstui.widgets.region_selector import RegionChanged, RegionSelector
from awstui.widgets.tags_pane import TagsPane, extract_tags


def _get_version() -> str:
    try:
        return _pkg_version("awstui")
    except PackageNotFoundError:
        return "unknown"


_SQL_MAX_ROWS = 1000
_SQL_MAX_COLUMNS = 100


def _escape_sql(value: str) -> str:
    """Escape single quotes for SQL string literal interpolation.

    Used for the boto3 credentials passed to DuckDB's SET statements
    (which don't accept parameter binding).
    """
    return value.replace("'", "''")


def _size_suffix(total: int, done: bool, count: int | None = None) -> str:
    """Return the label suffix for a node's size.

    e.g. ' (1.0 KB)' for a single object, ' (1.2 GB, 3,402 objects)' for a
    container, or ' (⋯ 1.2 GB, 1,201 objects)' while still climbing. `count`
    is None for leaf objects (an object is always one object, so the count
    would be noise); containers pass their running object count.
    """
    from awstui.util import human_bytes

    body = human_bytes(total)
    if count is not None:
        noun = "object" if count == 1 else "objects"
        body += f", {count:,} {noun}"
    return f" ({body})" if done else f" (⋯ {body})"


class AWSBrowserApp(App):
    """AWS TUI Browser."""

    TITLE = "awstui"
    BINDINGS = [
        Binding("1", "focus_region", "Region"),
        Binding("2", "focus_nav", "Nav"),
        Binding("3", "focus_detail", "Detail"),
        Binding("4", "focus_tags", "Tags"),
        Binding("a", "copy_arn", "Copy ARN"),
        Binding("u", "copy_uri", "Copy URI"),
        Binding("r", "copy_raw", "Copy Raw"),
        Binding("s", "toggle_size", "Size"),
        Binding("f", "filter_children", "Filter"),
        Binding("w", "toggle_content_wrap", "Wrap"),
        Binding("[", "shrink_pane", "Shrink"),
        Binding("]", "grow_pane", "Grow"),
    ]
    CSS = """
    #main {
        height: 1fr;
    }
    #nav-pane {
        width: 1fr;
        max-width: 40;
        min-width: 25;
        border-right: solid $primary;
    }
    #detail-pane {
        width: 2fr;
    }
    #tags-pane {
        width: 1fr;
        min-width: 25;
    }
    #identity-bar {
        dock: top;
        height: 1;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
    }
    #region-bar {
        dock: top;
        height: 3;
        padding: 0 1;
        background: $surface;
    }
    """

    def __init__(
        self,
        profile: str | None = None,
        services: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._profile: str | None = profile
        self._services: set[str] | None = (
            {s.lower() for s in services} if services else None
        )
        self._session: boto3.Session | None = None
        self._identity: str = ""
        self._region: str = "us-east-1"
        self._plugin_registry: PluginRegistry | None = None
        self._current_raw: object = {}
        self._current_subtitle: str = ""
        self._current_node: TreeNode | None = None
        self._selection_seq: int = 0
        self._current_container_node: TreeNode | None = None
        self._tag_summary_seq: int = -1
        self._content_seq: int = -1
        self._sql_seq: int = -1
        # id(textual TreeNode) -> label without the size suffix
        self._size_base_labels: dict[int, str] = {}
        # id(textual TreeNode) -> its in-flight size worker
        self._size_workers: dict[int, Worker] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._identity, id="identity-bar")
        with Horizontal(id="main"):
            with Vertical(id="nav-pane"):
                yield RegionSelector(self._region)
                yield AWSNavTree(self._session, [])  # placeholder, replaced on_mount
            yield DetailPane(id="detail-pane")
            yield TagsPane(id="tags-pane")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self._session = self._build_session()
            self._region = self._session.region_name or "us-east-1"
        except ProfileNotFound as e:
            self.query_one("#detail-pane", DetailPane).show_error(str(e))
            return
        except NoCredentialsError:
            self.query_one("#detail-pane", DetailPane).show_error(
                "No AWS credentials found. Configure credentials and restart."
            )
            return

        # Fetch identity
        try:
            sts = self._session.client("sts")
            identity = sts.get_caller_identity()
            self._identity = identity.get("Arn", "Unknown")
        except (ClientError, Exception):
            self._identity = "Unknown (could not fetch identity)"

        if self._profile:
            self._identity = f"[profile: {self._profile}] {self._identity}"

        self._identity = f"awstui v{_get_version()} · {self._identity}"

        self.query_one("#identity-bar", Static).update(self._identity)

        # Discover plugins and rebuild tree
        self._plugin_registry = discover_plugins()
        plugins = self._plugin_registry.list_plugins()
        if self._services is not None:
            plugins = [p for p in plugins if p.service_name.lower() in self._services]

        nav_pane = self.query_one("#nav-pane", Vertical)
        # Remove placeholder tree and region selector
        nav_pane.remove_children()
        # Mount fresh widgets
        nav_pane.mount(RegionSelector(self._region))
        tree = AWSNavTree(self._session, plugins)
        nav_pane.mount(tree)
        tree.focus()

    def on_node_selected(self, message: NodeSelected) -> None:
        try:
            self._handle_node_selected(message)
        finally:
            # The `a`/`u`/`r` footer entries depend on _current_raw /
            # _current_subtitle / _current_node — refresh their visibility
            # after any selection outcome.
            self.refresh_bindings()

    def _handle_node_selected(self, message: NodeSelected) -> None:
        detail = self.query_one("#detail-pane", DetailPane)
        tags = self.query_one("#tags-pane", TagsPane)
        node_data = message.node_data
        if self._plugin_registry is None:
            return
        plugin = self._plugin_registry.get(node_data.service)

        if plugin is None:
            detail.show_placeholder()
            tags.show_placeholder()
            self._current_raw = {}
            self._current_subtitle = ""
            self._current_node = None
            return

        self._selection_seq += 1
        seq = self._selection_seq
        self._current_container_node = None
        self._current_node = node_data
        self._current_raw = {}
        self._current_subtitle = ""

        if node_data.node_type == "service":
            resource_details = ResourceDetails(
                title=plugin.name,
                subtitle=f"boto3 service: {plugin.service_name}",
                summary={},
                raw={},
            )
            if plugin.has_flat_root:
                detail.show_details(
                    resource_details,
                    empty_summary_status="Retrieving count ...",
                    include_tag_summary=True,
                )
                self._current_container_node = node_data
                self._load_child_count(node_data, seq)
            else:
                detail.show_details(resource_details)
            tags.show_placeholder()
            return

        # plugin.get_details makes AWS calls (e.g. get_bucket_location,
        # get_bucket_tagging) which can each take 100ms+. Doing it off-thread
        # keeps arrow-key navigation snappy. Show a placeholder immediately
        # so the user gets feedback, then render the real details when they
        # land — with seq check to drop stale results from rapid navigation.
        loading = ResourceDetails(
            title=node_data.label,
            subtitle="Loading ...",
            summary={},
            raw={},
        )
        detail.show_details(loading, empty_summary_status="Loading details ...")
        tags.show_placeholder()
        self._load_details(node_data, seq)

    def on_node_error(self, message: NodeError) -> None:
        self.query_one("#detail-pane", DetailPane).show_error(message.error_message)
        self.query_one("#tags-pane", TagsPane).show_placeholder()
        self._current_raw = {}
        self._current_subtitle = ""
        self._current_node = None
        self._selection_seq += 1
        self.refresh_bindings()

    def on_tree_node_expanded(self, event) -> None:
        """When a sized node is expanded, cascade sizing to its children.

        Bubbles up after AWSNavTree.on_tree_node_expanded has synchronously
        added the children, so they are present here. Each child that is
        sizeable and not already sized gets turned on.
        """
        node = event.node
        if id(node) not in self._size_base_labels:
            return
        for child in node.children:
            if id(child) in self._size_base_labels:
                continue
            data = getattr(child, "data", None)
            if data is None or not self._size_supported(data):
                continue
            self._size_on(child)

    def action_focus_region(self) -> None:
        try:
            self.query_one(RegionSelector).focus()
        except Exception:
            pass

    def action_focus_nav(self) -> None:
        try:
            self.query_one(AWSNavTree).focus()
        except Exception:
            pass

    def action_focus_detail(self) -> None:
        try:
            self.query_one("#detail-pane", DetailPane).focus()
        except Exception:
            pass

    def action_focus_tags(self) -> None:
        try:
            self.query_one("#tags-pane", TagsPane).focus()
        except Exception:
            pass

    PANE_IDS = ("nav-pane", "detail-pane", "tags-pane")
    PANE_RESIZE_STEP = 4
    PANE_MIN_WIDTH = 20

    def _focused_pane(self):
        widget = self.focused
        while widget is not None:
            if widget.id in self.PANE_IDS:
                return widget
            widget = widget.parent
        return None

    def _resize_focused_pane(self, delta: int) -> None:
        pane = self._focused_pane()
        if pane is None:
            return
        current = pane.size.width
        new_width = max(self.PANE_MIN_WIDTH, current + delta)
        pane.styles.width = new_width
        if pane.id == "nav-pane":
            # Override the CSS max-width constraint so nav can grow freely.
            pane.styles.max_width = new_width

    def action_shrink_pane(self) -> None:
        self._resize_focused_pane(-self.PANE_RESIZE_STEP)

    def action_grow_pane(self) -> None:
        self._resize_focused_pane(self.PANE_RESIZE_STEP)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Hide copy bindings from the footer when the current selection
        doesn't expose the thing they'd copy.

        See https://textual.textualize.io/guide/actions#dynamic-actions
        """
        if action == "copy_arn":
            return bool(self._current_arn())
        if action == "copy_uri":
            return bool(self._current_uri())
        if action == "copy_raw":
            return bool(self._current_raw)
        if action == "toggle_size":
            return bool(
                self._current_node is not None
                and self._size_supported(self._current_node)
            )
        return True

    def _current_arn(self) -> str:
        arn = self._find_arn(self._current_raw)
        if not arn and self._current_subtitle.startswith("arn:"):
            arn = self._current_subtitle
        return arn

    def _current_uri(self) -> str:
        return self._uri_for(self._current_node)

    def action_copy_arn(self) -> None:
        arn = self._current_arn()
        if not arn:
            self.notify("No ARN available for this resource", severity="warning")
            return
        self._copy_text(arn, f"Copied ARN: {arn}")

    def action_copy_uri(self) -> None:
        uri = self._current_uri()
        if not uri:
            self.notify("No URI available for this resource", severity="warning")
            return
        self._copy_text(uri, f"Copied URI: {uri}")

    def action_filter_children(self) -> None:
        tree = self.query_one(AWSNavTree)
        parent = tree.cursor_node
        if parent is None or parent is tree.root:
            self.notify(
                "Select a parent node in the navigation tree first",
                severity="warning",
            )
            return
        if not parent.allow_expand:
            self.notify("Selected node has no children to filter", severity="warning")
            return
        if not parent.children:
            self.notify(
                "No children loaded yet — expand the node first",
                severity="warning",
            )
            return

        def apply(substring: str | None) -> None:
            if substring is None:
                return
            count = tree.filter_children(parent, substring)
            if not substring:
                self.notify("Filter cleared")
            else:
                noun = "match" if count == 1 else "matches"
                self.notify(f"{count} {noun} for '{substring}'")

        self.push_screen(FilterDialog(), apply)

    @staticmethod
    def _uri_for(node: TreeNode | None) -> str:
        if node is None:
            return ""
        meta = node.metadata
        if node.node_type == "bucket":
            bucket = meta.get("bucket_name", "")
            return f"s3://{bucket}" if bucket else ""
        if node.node_type == "object":
            bucket = meta.get("bucket_name", "")
            key = meta.get("key", "")
            return f"s3://{bucket}/{key}" if bucket and key else ""
        if node.node_type in ("private_image", "public_image"):
            repo_uri = meta.get("repository_uri", "")
            if not repo_uri:
                return ""
            tags = meta.get("image_tags") or []
            if tags:
                return f"{repo_uri}:{tags[0]}"
            digest = meta.get("image_digest", "")
            return f"{repo_uri}@{digest}" if digest else repo_uri
        return ""

    def action_copy_raw(self) -> None:
        if not self._current_raw:
            self.notify("No raw JSON available for this resource", severity="warning")
            return
        raw = json.dumps(self._current_raw, indent=2, default=str)
        self._copy_text(raw, "Copied raw JSON")

    def action_toggle_content_wrap(self) -> None:
        try:
            detail = self.query_one("#detail-pane", DetailPane)
        except Exception:
            return
        if detail._content_preview is None:
            self.notify("No content loaded to wrap", severity="warning")
            return
        wrapped = detail.toggle_content_wrap()
        self.notify(f"Content wrap: {'on' if wrapped else 'off'}")

    def _copy_text(self, text: str, success_message: str) -> None:
        try:
            pyperclip.copy(text)
            self.notify(success_message)
        except pyperclip.PyperclipException:
            # No system clipboard tool available — fall back to OSC 52.
            self.copy_to_clipboard(text)
            self.notify(
                f"{success_message} (via terminal escape)",
                severity="warning",
            )

    @staticmethod
    def _noun_for(label: str) -> str:
        """Derive a lowercase noun from a container node label.

        'Users' -> 'users', 'DB Instances' -> 'instances',
        'Attached Policies' -> 'policies', 'Access Keys' -> 'keys'.
        """
        last = label.strip().split()[-1] if label.strip() else "items"
        return last.lower()

    @staticmethod
    def _pluralize(word: str) -> str:
        if not word:
            return "items"
        if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
            return word[:-1] + "ies"
        if word.endswith(("s", "x", "z", "ch", "sh")):
            return word + "es"
        return word + "s"

    def _size_supported(self, node: TreeNode) -> bool:
        if self._plugin_registry is None:
            return False
        plugin = self._plugin_registry.get(node.service)
        return bool(plugin and plugin.supports_size(node))

    _SIZE_UNAVAILABLE_SUFFIX = " (size unavailable)"

    def action_toggle_size(self) -> None:
        tree = self.query_one(AWSNavTree)
        node = tree.cursor_node
        if node is None or node.data is None:
            return
        if not self._size_supported(node.data):
            self.notify("Size not available for this node", severity="warning")
            return
        if id(node) in self._size_base_labels:
            self._size_off(node)
        else:
            self._size_on(node)

    # NB: the `node` argument to the size helpers below is a *Textual* tree
    # node (it has .label / .set_label / .children); its `.data` is the
    # awstui.models.TreeNode. Don't confuse the two — both are named TreeNode.
    def _size_on(self, node) -> None:
        """Start sizing `node`: record its base label and spawn a worker."""
        base = str(node.label)
        self._size_base_labels[id(node)] = base
        node.set_label(base + " (⋯)")
        self._size_workers[id(node)] = self._size_worker(node, node.data)

    def _size_off(self, node) -> None:
        """Stop sizing `node` and every descendant it cascaded to."""
        for descendant in list(self._iter_sized_descendants(node)):
            self._cancel_size(descendant)
        self._cancel_size(node)

    def _cancel_all_sizes(self) -> None:
        """Cancel every in-flight size walk and forget all size state.

        Called on region switch / tree reset — computed sizes are
        meaningless against a new session, and the tree nodes are gone.
        """
        for worker in self._size_workers.values():
            worker.cancel()
        self._size_workers.clear()
        self._size_base_labels.clear()

    def _cancel_size(self, node) -> None:
        worker = self._size_workers.pop(id(node), None)
        if worker is not None:
            worker.cancel()
        base = self._size_base_labels.pop(id(node), None)
        if base is not None:
            node.set_label(base)

    def _iter_sized_descendants(self, node):
        """Yield textual descendants of `node` that are currently sized."""
        for child in getattr(node, "children", []):
            if id(child) in self._size_base_labels:
                yield child
            yield from self._iter_sized_descendants(child)

    def _set_node_size(self, node, total: int, done: bool, count: int) -> None:
        base = self._size_base_labels.get(id(node))
        if base is None:
            # Toggled off (or region-switched) while the walk was in flight.
            return
        # A leaf object is always one object — showing the count is noise, so
        # only containers (buckets / prefixes) display it.
        data = getattr(node, "data", None)
        show_count = (
            None if (data is not None and data.node_type == "object") else count
        )
        node.set_label(base + _size_suffix(total, done, show_count))

    def _set_node_size_unavailable(self, node) -> None:
        base = self._size_base_labels.get(id(node))
        if base is None:
            return
        node.set_label(base + self._SIZE_UNAVAILABLE_SUFFIX)

    @work(thread=True, group="size")
    def _size_worker(self, node, data: TreeNode) -> None:
        plugin = (
            self._plugin_registry.get(data.service) if self._plugin_registry else None
        )
        if plugin is None or self._session is None:
            return
        worker = get_current_worker()
        total = 0
        count = 0
        try:
            for total, count in plugin.iter_size(self._session, data):
                if worker.is_cancelled:
                    return
                self.call_from_thread(self._set_node_size, node, total, False, count)
            self.call_from_thread(self._set_node_size, node, total, True, count)
        except ClientError:
            self.call_from_thread(self._set_node_size_unavailable, node)
        except Exception:
            self.call_from_thread(self._set_node_size_unavailable, node)

    @work(thread=True, exclusive=True, group="details")
    def _load_details(self, node: TreeNode, seq: int) -> None:
        plugin = (
            self._plugin_registry.get(node.service) if self._plugin_registry else None
        )
        if plugin is None or self._session is None:
            return
        try:
            details = plugin.get_details(self._session, node)
        except ClientError as e:
            error_code = e.response["Error"].get("Code", "")
            if error_code in (
                "AccessDenied",
                "AccessDeniedException",
                "UnauthorizedAccess",
            ):
                msg = f"Access Denied: insufficient permissions to view {node.label}"
            else:
                msg = f"Error loading details: {e}"
            self.call_from_thread(self._apply_details_error, seq, msg)
            return
        except Exception as e:
            self.call_from_thread(
                self._apply_details_error, seq, f"Error loading details: {e}"
            )
            return
        self.call_from_thread(self._apply_details, seq, node, details)

    def _apply_details(
        self, seq: int, node: TreeNode, details: ResourceDetails
    ) -> None:
        if seq != self._selection_seq:
            return
        detail = self.query_one("#detail-pane", DetailPane)
        tags = self.query_one("#tags-pane", TagsPane)

        plugin = (
            self._plugin_registry.get(node.service) if self._plugin_registry else None
        )
        is_container = not details.summary and node.expandable
        include_content = plugin.has_content(node) if plugin else False
        include_sql = plugin.has_sql(node) if plugin else False
        default_sql = plugin.default_sql(node) if (plugin and include_sql) else ""

        if is_container:
            detail.show_details(
                details,
                empty_summary_status="Retrieving count ...",
                include_tag_summary=True,
                include_content=include_content,
                include_sql=include_sql,
                default_sql=default_sql or "",
            )
            self._current_container_node = node
        else:
            detail.show_details(
                details,
                include_content=include_content,
                include_sql=include_sql,
                default_sql=default_sql or "",
            )
        self._current_raw = details.raw
        self._current_subtitle = details.subtitle
        tags.show_tags(details.raw)
        self.refresh_bindings()

        if is_container:
            self._load_child_count(node, seq)

    def _apply_details_error(self, seq: int, message: str) -> None:
        if seq != self._selection_seq:
            return
        self.query_one("#detail-pane", DetailPane).show_error(message)
        self.query_one("#tags-pane", TagsPane).show_placeholder()
        self._current_raw = {}
        self._current_subtitle = ""
        self.refresh_bindings()

    @work(thread=True, exclusive=True, group="child_count")
    def _load_child_count(self, node: TreeNode, seq: int) -> None:
        plugin = (
            self._plugin_registry.get(node.service) if self._plugin_registry else None
        )
        if plugin is None or self._session is None:
            return

        try:
            if node.node_type == "service":
                children = plugin.get_root_nodes(self._session)
                # Derive noun from the first child's node_type (e.g. 'bucket', 'function').
                # Falls back to the plugin name if there are no children.
                base = (
                    children[0].node_type.replace("_", " ")
                    if children
                    else plugin.name.lower()
                )
                noun = self._pluralize(base)
            else:
                children = plugin.get_children(self._session, node)
                noun = self._noun_for(node.label)
            count = len(children)
            message = f"{count} {noun}"
        except ClientError as e:
            error_code = e.response["Error"].get("Code", "")
            if error_code in (
                "AccessDenied",
                "AccessDeniedException",
                "UnauthorizedAccess",
            ):
                message = "Access Denied: cannot count items"
            else:
                message = f"Error counting items: {e}"
        except Exception as e:
            message = f"Error counting items: {e}"

        self.call_from_thread(self._apply_child_count, seq, message)

    def _apply_child_count(self, seq: int, message: str) -> None:
        # Drop stale results if the user has since selected a different node.
        if seq != self._selection_seq:
            return
        try:
            self.query_one("#detail-pane", DetailPane).set_summary_status(message)
        except Exception:
            pass

    @work(thread=True, exclusive=True, group="tag_summary")
    def _load_tag_summary(self, node: TreeNode, seq: int) -> None:
        plugin = (
            self._plugin_registry.get(node.service) if self._plugin_registry else None
        )
        if plugin is None or self._session is None:
            return

        try:
            if node.node_type == "service":
                children = plugin.get_root_nodes(self._session)
            else:
                children = plugin.get_children(self._session, node)
        except Exception as e:
            self.call_from_thread(self._apply_tag_summary, seq, {"Error": f"{e}"})
            return

        self.call_from_thread(self._start_tag_summary_progress, seq, len(children))

        aggregated: dict[str, dict[str, int]] = {}
        for child in children:
            try:
                child_details = plugin.get_details(self._session, child)
            except Exception:
                self.call_from_thread(self._advance_tag_summary_progress, seq)
                continue
            for k, v in extract_tags(child_details.raw).items():
                counts = aggregated.setdefault(k, {})
                counts[v] = counts.get(v, 0) + 1
            self.call_from_thread(self._advance_tag_summary_progress, seq)

        self.call_from_thread(self._apply_tag_summary, seq, aggregated)

    def _apply_tag_summary(
        self, seq: int, aggregated: dict[str, dict[str, int]]
    ) -> None:
        if seq != self._selection_seq:
            return
        try:
            self.query_one("#detail-pane", DetailPane).set_tag_summary(aggregated)
        except Exception:
            pass

    def _start_tag_summary_progress(self, seq: int, total: int) -> None:
        if seq != self._selection_seq:
            return
        try:
            self.query_one("#detail-pane", DetailPane).start_tag_summary_progress(total)
        except Exception:
            pass

    def _advance_tag_summary_progress(self, seq: int) -> None:
        if seq != self._selection_seq:
            return
        try:
            self.query_one("#detail-pane", DetailPane).advance_tag_summary_progress()
        except Exception:
            pass

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        if event.pane.id == "tab-tag-summary":
            self._handle_tag_summary_tab_activated()
        elif event.pane.id == "tab-content":
            self._handle_content_tab_activated()

    def _handle_tag_summary_tab_activated(self) -> None:
        if self._current_container_node is None:
            return
        try:
            tag_pane = self.query_one("#tab-tag-summary", TabPane)
        except Exception:
            return
        # Only fetch once per selection — re-activating an already-populated
        # tab shouldn't re-trigger the work.
        if self._tag_summary_seq == self._selection_seq:
            return
        self._tag_summary_seq = self._selection_seq
        try:
            status = tag_pane.query_one(".tag-summary-status", Static)
            status.update("Retrieving tag summary ...")
        except Exception:
            tag_pane.mount(
                Static("Retrieving tag summary ...", classes="tag-summary-status")
            )
        self._load_tag_summary(self._current_container_node, self._selection_seq)

    def _handle_content_tab_activated(self) -> None:
        if self._current_node is None:
            return
        if self._content_seq == self._selection_seq:
            return
        self._content_seq = self._selection_seq
        try:
            self.query_one("#detail-pane", DetailPane).set_content_status(
                "Loading content ..."
            )
        except Exception:
            pass
        self._load_content(self._current_node, self._selection_seq)

    @work(thread=True, exclusive=True, group="content")
    def _load_content(self, node: TreeNode, seq: int) -> None:
        plugin = (
            self._plugin_registry.get(node.service) if self._plugin_registry else None
        )
        if plugin is None or self._session is None:
            return
        try:
            preview = plugin.get_content(self._session, node)
        except ClientError as e:
            error_code = e.response["Error"].get("Code", "")
            if error_code in (
                "AccessDenied",
                "AccessDeniedException",
                "UnauthorizedAccess",
            ):
                msg = "Access Denied: insufficient permissions to load content"
            else:
                msg = f"Error loading content: {e}"
            self.call_from_thread(self._apply_content_error, seq, msg)
            return
        except Exception as e:
            self.call_from_thread(self._apply_content_error, seq, f"Error: {e}")
            return
        self.call_from_thread(self._apply_content, seq, preview)

    def _apply_content(self, seq: int, preview: ContentPreview | None) -> None:
        if seq != self._selection_seq:
            return
        detail = self.query_one("#detail-pane", DetailPane)
        if preview is None:
            detail.set_content_status("No content available for this resource")
            return
        detail.set_content_preview(preview)

    def _apply_content_error(self, seq: int, message: str) -> None:
        if seq != self._selection_seq:
            return
        try:
            self.query_one("#detail-pane", DetailPane).set_content_status(message)
        except Exception:
            pass

    # ----- SQL tab -----

    def on_sql_submit(self, message) -> None:
        """Run a query submitted from the SQL tab off-thread."""
        self._sql_seq = self._selection_seq
        sql_pane = self._sql_pane()
        if sql_pane is not None:
            sql_pane.set_running()
        if self._session is None:
            self._apply_sql_error(self._sql_seq, "No AWS session")
            return
        self._run_sql(message.query, self._session, self._sql_seq)

    def _sql_pane(self):
        try:
            from awstui.widgets.sql_pane import SqlPaneContent

            return self.query_one(SqlPaneContent)
        except Exception:
            return None

    @work(thread=True, exclusive=True, group="sql")
    def _run_sql(self, query: str, session: boto3.Session, seq: int) -> None:
        try:
            import duckdb  # lazy: heavy native dep
        except ImportError:
            self.call_from_thread(
                self._apply_sql_error,
                seq,
                "duckdb is not installed — install it to use the SQL tab",
            )
            return

        try:
            credentials = session.get_credentials()
            frozen = credentials.get_frozen_credentials() if credentials else None
            region = session.region_name or "us-east-1"

            con = duckdb.connect()
            con.execute("INSTALL httpfs")
            con.execute("LOAD httpfs")
            con.execute(f"SET s3_region = '{_escape_sql(region)}'")
            if frozen is not None:
                con.execute(
                    f"SET s3_access_key_id = '{_escape_sql(frozen.access_key)}'"
                )
                con.execute(
                    f"SET s3_secret_access_key = '{_escape_sql(frozen.secret_key)}'"
                )
                if frozen.token:
                    con.execute(f"SET s3_session_token = '{_escape_sql(frozen.token)}'")

            cursor = con.execute(query)
            description = cursor.description or []
            columns = [d[0] for d in description]
            rows = cursor.fetchmany(_SQL_MAX_ROWS + 1)
            truncated = len(rows) > _SQL_MAX_ROWS
            rows = rows[:_SQL_MAX_ROWS]
            visible_columns = columns[:_SQL_MAX_COLUMNS]
            visible_rows = [tuple(r[: len(visible_columns)]) for r in rows]
        except Exception as e:
            self.call_from_thread(
                self._apply_sql_error, seq, f"{type(e).__name__}: {e}"
            )
            return

        self.call_from_thread(
            self._apply_sql_result,
            seq,
            visible_columns,
            visible_rows,
            truncated,
            len(columns),
        )

    def _apply_sql_result(
        self,
        seq: int,
        columns: list[str],
        rows: list[tuple],
        truncated: bool,
        total_columns: int,
    ) -> None:
        if seq != self._selection_seq:
            return
        sql_pane = self._sql_pane()
        if sql_pane is not None:
            sql_pane.set_result(columns, rows, truncated, total_columns)

    def _apply_sql_error(self, seq: int, message: str) -> None:
        if seq != self._selection_seq:
            return
        sql_pane = self._sql_pane()
        if sql_pane is not None:
            sql_pane.set_error(message)

    def _find_arn(self, obj: object) -> str:
        """Recursively find an ARN in a raw API response.

        Looks for a key whose name (case-insensitive) ends with 'arn'
        and whose value is a string starting with 'arn:'.
        """
        if isinstance(obj, dict):
            for key, value in obj.items():
                if (
                    isinstance(key, str)
                    and key.lower().endswith("arn")
                    and isinstance(value, str)
                    and value.startswith("arn:")
                ):
                    return value
            for value in obj.values():
                found = self._find_arn(value)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = self._find_arn(item)
                if found:
                    return found
        return ""

    def _build_session(self, region_name: str | None = None) -> boto3.Session:
        kwargs: dict[str, str] = {}
        if self._profile:
            kwargs["profile_name"] = self._profile
        if region_name:
            kwargs["region_name"] = region_name
        return boto3.Session(**kwargs)

    def on_region_changed(self, message: RegionChanged) -> None:
        if message.region == self._region:
            return

        self._region = message.region
        self._session = self._build_session(region_name=self._region)

        tree = self.query_one(AWSNavTree)
        tree.session = self._session
        tree.reset_tree()

        self.query_one("#detail-pane", DetailPane).show_placeholder()
        self.query_one("#tags-pane", TagsPane).show_placeholder()
        self._current_raw = {}
        self._current_subtitle = ""
        self._current_node = None
        self._selection_seq += 1
        self._current_container_node = None
        self._cancel_all_sizes()
        self.refresh_bindings()
