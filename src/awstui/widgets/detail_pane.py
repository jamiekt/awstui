from __future__ import annotations

import json

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import ProgressBar, Static, TabbedContent, TabPane

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

    def show_details(
        self,
        details: ResourceDetails,
        empty_summary_status: str = "No summary available",
        include_tag_summary: bool = False,
    ) -> None:
        """Display resource details with Summary, Raw JSON, and optionally Tag Summary tabs.

        `empty_summary_status` is the text shown in the Summary tab when
        `details.summary` is empty (e.g. "Retrieving count ..." while a
        child-count fetch is in flight).

        `include_tag_summary` adds a third "Tag Summary" tab that stays empty
        until the caller populates it via `set_tag_summary`.
        """
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

        if include_tag_summary:
            tag_pane = TabPane("Tag Summary", id="tab-tag-summary")
            tabbed.add_pane(tag_pane)
            tag_pane.mount(
                Static(
                    "Select this tab to load tag summary",
                    classes="tag-summary-status",
                )
            )

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
            summary_pane.mount(Static(empty_summary_status, id="summary-status"))

        raw_json = json.dumps(details.raw, indent=2, default=str)
        raw_pane.mount(
            VerticalScroll(
                Static(Syntax(raw_json, "json", theme="monokai", line_numbers=False))
            )
        )

    def set_summary_status(self, message: str) -> None:
        """Update the summary status line (used for lazy-loaded counts)."""
        try:
            self.query_one("#summary-status", Static).update(message)
        except Exception:
            pass

    def start_tag_summary_progress(self, total: int) -> None:
        """Replace the Tag Summary tab with a progress bar."""
        try:
            tag_pane = self.query_one("#tab-tag-summary", TabPane)
        except Exception:
            return
        for child in list(tag_pane.children):
            child.remove()
        tag_pane.mount(
            Static(
                f"Retrieving tag summary for {total} items ...",
                classes="tag-summary-status",
            )
        )
        tag_pane.mount(ProgressBar(total=total, show_eta=False, id="tag-progress"))

    def advance_tag_summary_progress(self, amount: int = 1) -> None:
        """Advance the tag-summary progress bar."""
        try:
            self.query_one("#tag-progress", ProgressBar).advance(amount)
        except Exception:
            pass

    def set_tag_summary(self, rows: dict[str, str]) -> None:
        """Replace the Tag Summary tab content with one row per tag key."""
        try:
            tag_pane = self.query_one("#tab-tag-summary", TabPane)
        except Exception:
            return
        # Remove the placeholder Static (if present) and any previously
        # mounted rows. Use .remove() per child so IDs are freed synchronously
        # before we mount replacements.
        for child in list(tag_pane.children):
            child.remove()
        if not rows:
            tag_pane.mount(Static("No tags found", classes="tags-empty"))
            return
        for label, value in rows.items():
            tag_pane.mount(
                Static(
                    Text.assemble(
                        (f"{label}: ", "bold dim"),
                        (str(value), ""),
                    ),
                    classes="summary-row",
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
