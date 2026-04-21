from __future__ import annotations

import boto3
import pyperclip
from botocore.exceptions import ClientError, NoCredentialsError
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from awstui.models import ResourceDetails
from awstui.services import discover_plugins
from awstui.widgets.detail_pane import DetailPane
from awstui.widgets.nav_tree import AWSNavTree, NodeError, NodeSelected
from awstui.widgets.region_selector import RegionChanged, RegionSelector


class AWSBrowserApp(App):
    """AWS TUI Browser."""

    TITLE = "awstui"
    BINDINGS = [
        Binding("1", "focus_region", "Region"),
        Binding("2", "focus_nav", "Nav"),
        Binding("3", "focus_detail", "Detail"),
        Binding("c", "copy_arn", "Copy ARN"),
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

    def __init__(self) -> None:
        super().__init__()
        self._session: boto3.Session | None = None
        self._identity: str = ""
        self._region: str = "us-east-1"
        self._plugin_registry = None
        self._current_raw: object = {}

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
            self._session = boto3.Session()
            self._region = self._session.region_name or "us-east-1"
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

        if node_data.node_type == "service":
            detail.show_details(
                ResourceDetails(
                    title=plugin.name,
                    subtitle=f"boto3 service: {plugin.service_name}",
                    summary={},
                    raw={},
                )
            )
            self._current_raw = {}
            return

        try:
            details = plugin.get_details(self._session, node_data)
            detail.show_details(details)
            self._current_raw = details.raw
        except ClientError as e:
            error_code = e.response["Error"].get("Code", "")
            if error_code in ("AccessDenied", "AccessDeniedException", "UnauthorizedAccess"):
                detail.show_error(f"Access Denied: insufficient permissions to view {node_data.label}")
            else:
                detail.show_error(f"Error loading details: {e}")
            self._current_raw = {}
        except Exception as e:
            detail.show_error(f"Error loading details: {e}")
            self._current_raw = {}

    def on_node_error(self, message: NodeError) -> None:
        self.query_one("#detail-pane", DetailPane).show_error(message.error_message)
        self._current_raw = {}

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
        try:
            pyperclip.copy(arn)
            self.notify(f"Copied ARN: {arn}")
        except pyperclip.PyperclipException:
            # No system clipboard tool available — fall back to OSC 52.
            self.copy_to_clipboard(arn)
            self.notify(
                f"Copied ARN via terminal escape: {arn}",
                severity="warning",
            )

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

    def on_region_changed(self, message: RegionChanged) -> None:
        if message.region == self._region:
            return

        self._region = message.region
        self._session = boto3.Session(region_name=self._region)

        tree = self.query_one(AWSNavTree)
        tree.session = self._session
        tree.reset_tree()

        self.query_one("#detail-pane", DetailPane).show_placeholder()
        self._current_raw = {}
