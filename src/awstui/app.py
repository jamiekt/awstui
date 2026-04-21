from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version as _pkg_version

import boto3
import pyperclip
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static
from textual import work

from awstui.models import ResourceDetails, TreeNode
from awstui.services import discover_plugins
from awstui.widgets.detail_pane import DetailPane
from awstui.widgets.nav_tree import AWSNavTree, NodeError, NodeSelected
from awstui.widgets.region_selector import RegionChanged, RegionSelector


def _get_version() -> str:
    try:
        return _pkg_version("awstui")
    except PackageNotFoundError:
        return "unknown"


class AWSBrowserApp(App):
    """AWS TUI Browser."""

    TITLE = "awstui"
    BINDINGS = [
        Binding("1", "focus_region", "Region"),
        Binding("2", "focus_nav", "Nav"),
        Binding("3", "focus_detail", "Detail"),
        Binding("c", "copy_arn", "Copy ARN"),
        Binding("r", "copy_raw", "Copy Raw"),
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
        width: 3fr;
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

    def __init__(self, profile: str | None = None) -> None:
        super().__init__()
        self._profile: str | None = profile
        self._session: boto3.Session | None = None
        self._identity: str = ""
        self._region: str = "us-east-1"
        self._plugin_registry = None
        self._current_raw: object = {}
        self._selection_seq: int = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._identity, id="identity-bar")
        with Horizontal(id="main"):
            with Vertical(id="nav-pane"):
                yield RegionSelector(self._region)
                yield AWSNavTree(self._session, [])  # placeholder, replaced on_mount
            yield DetailPane(id="detail-pane")
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

        nav_pane = self.query_one("#nav-pane", Vertical)
        # Remove placeholder tree and region selector
        nav_pane.remove_children()
        # Mount fresh widgets
        nav_pane.mount(RegionSelector(self._region))
        tree = AWSNavTree(self._session, plugins)
        nav_pane.mount(tree)
        tree.focus()

    def on_node_selected(self, message: NodeSelected) -> None:
        detail = self.query_one("#detail-pane", DetailPane)
        node_data = message.node_data
        if self._plugin_registry is None:
            return
        plugin = self._plugin_registry.get(node_data.service)

        if plugin is None:
            detail.show_placeholder()
            self._current_raw = {}
            return

        self._selection_seq += 1

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
                )
                self._current_raw = {}
                self._load_child_count(node_data, self._selection_seq)
            else:
                detail.show_details(resource_details)
                self._current_raw = {}
            return

        try:
            details = plugin.get_details(self._session, node_data)
        except ClientError as e:
            error_code = e.response["Error"].get("Code", "")
            if error_code in (
                "AccessDenied",
                "AccessDeniedException",
                "UnauthorizedAccess",
            ):
                detail.show_error(
                    f"Access Denied: insufficient permissions to view {node_data.label}"
                )
            else:
                detail.show_error(f"Error loading details: {e}")
            self._current_raw = {}
            return
        except Exception as e:
            detail.show_error(f"Error loading details: {e}")
            self._current_raw = {}
            return

        # For container nodes (no summary of their own), show a fetching
        # placeholder *at mount time* and kick off a background count.
        is_container = not details.summary and node_data.expandable
        if is_container:
            detail.show_details(details, empty_summary_status="Retrieving count ...")
        else:
            detail.show_details(details)
        self._current_raw = details.raw

        if is_container:
            self._load_child_count(node_data, self._selection_seq)

    def on_node_error(self, message: NodeError) -> None:
        self.query_one("#detail-pane", DetailPane).show_error(message.error_message)
        self._current_raw = {}
        self._selection_seq += 1

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

    def action_copy_arn(self) -> None:
        arn = self._find_arn(self._current_raw)
        if not arn:
            self.notify("No ARN available for this resource", severity="warning")
            return
        self._copy_text(arn, f"Copied ARN: {arn}")

    def action_copy_raw(self) -> None:
        if not self._current_raw:
            self.notify("No raw JSON available for this resource", severity="warning")
            return
        raw = json.dumps(self._current_raw, indent=2, default=str)
        self._copy_text(raw, "Copied raw JSON")

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
        self._current_raw = {}
        self._selection_seq += 1
