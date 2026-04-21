from __future__ import annotations

import json

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static, TabbedContent, TabPane

from awstui.models import ResourceDetails


class DetailPane(Static, can_focus=True):
    """Right pane showing details of the selected resource."""

    DEFAULT_CSS = """
    DetailPane {
        height: 100%;
        padding: 1;
    }
    DetailPane:focus {
        border: tall $accent;
        padding: 0;
    }
    .detail-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 0;
    }
    .detail-subtitle {
        color: $text-muted;
        margin-bottom: 1;
    }
    .detail-error {
        color: $error;
        margin: 2;
    }
    .summary-row {
        margin-bottom: 0;
    }
    .summary-label {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Select a resource to view details")

    def show_details(self, details: ResourceDetails) -> None:
        """Display resource details with Summary and Raw JSON tabs."""
        self.remove_children()

        self.mount(Static(details.title, classes="detail-title"))
        if details.subtitle:
            self.mount(Static(details.subtitle, classes="detail-subtitle"))

        tabbed = TabbedContent()
        self.mount(tabbed)

        summary_pane = TabPane("Summary", id="tab-summary")
        raw_pane = TabPane("Raw JSON", id="tab-raw")

        tabbed.add_pane(summary_pane)
        tabbed.add_pane(raw_pane)

        if details.summary:
            for label, value in details.summary.items():
                summary_pane.mount(
                    Static(
                        Text.assemble(
                            (f"{label}: ", "bold dim"),
                            (str(value), ""),
                        ),
                        classes="summary-row",
                    )
                )
        else:
            summary_pane.mount(Static("No summary available"))

        raw_json = json.dumps(details.raw, indent=2, default=str)
        raw_pane.mount(
            VerticalScroll(
                Static(Syntax(raw_json, "json", theme="monokai", line_numbers=False))
            )
        )

    def show_error(self, message: str) -> None:
        """Display an error message."""
        self.remove_children()
        self.mount(Static(message, classes="detail-error"))

    def show_placeholder(self) -> None:
        """Show the default placeholder."""
        self.remove_children()
        self.mount(Static("Select a resource to view details"))
