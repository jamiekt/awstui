from __future__ import annotations

import json

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import ProgressBar, Static, TabbedContent, TabPane

from awstui.models import ResourceDetails


def _tag_segment_colors(count: int) -> list[str]:
    """Generate `count` visually distinct hex colors via HSL hue rotation."""
    if count <= 0:
        return []
    import colorsys

    golden = 0.61803398875
    sat_light = [(0.65, 0.55), (0.70, 0.45)]
    colors: list[str] = []
    hue = 0.08
    for i in range(count):
        s, light = sat_light[i % len(sat_light)]
        r, g, b = colorsys.hls_to_rgb(hue, light, s)
        colors.append(f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
        hue = (hue + golden) % 1.0
    return colors


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
    .tag-summary-key {
        text-style: bold;
        color: $accent;
        height: 1;
        margin-right: 1;
    }
    .tag-summary-bar {
        color: $text;
    }
    .tag-summary-row {
        height: 1;
        margin-bottom: 0;
    }
    .tag-summary-bar-stack {
        height: 1;
    }
    .tag-summary-segment {
        height: 1;
        overflow: hidden;
    }
    .tag-summary-total {
        width: auto;
        margin-left: 1;
        color: $text-muted;
    }
    .tag-summary-bar-area {
        width: 1fr;
        height: 1;
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

    def set_tag_summary(self, aggregated: dict[str, dict[str, int]]) -> None:
        """Render the Tag Summary tab as horizontal stacked bar charts.

        `aggregated` is {tag_key: {tag_value: count_of_resources}}.
        Each tag key gets one stacked bar. Each value is a colored segment
        sized proportionally to its count. Hovering a segment shows a
        tooltip with the value and count.
        """
        try:
            tag_pane = self.query_one("#tab-tag-summary", TabPane)
        except Exception:
            return
        # Remove the placeholder / progress bar / previous rows synchronously
        # so IDs are freed before we mount replacements.
        for child in list(tag_pane.children):
            child.remove()
        if not aggregated:
            tag_pane.mount(Static("No tags found", classes="tags-empty"))
            return

        scroll = VerticalScroll()
        tag_pane.mount(scroll)

        max_total = max(sum(v.values()) for v in aggregated.values())
        # Reserve one column per character of the longest key so every bar
        # starts at the same column.
        key_width = max(len(k) for k in aggregated)
        for key in sorted(aggregated):
            counts = aggregated[key]
            total = sum(counts.values())
            ordered = sorted(counts.items(), key=lambda kv: -kv[1])
            palette = _tag_segment_colors(len(ordered))

            segments: list[Static] = []
            for (value, count), color in zip(ordered, palette, strict=True):
                seg = Static(value, classes="tag-summary-segment")
                seg.styles.background = color
                seg.styles.width = f"{count}fr"
                seg.tooltip = f"{value}: {count}"
                segments.append(seg)

            # The bar itself is a container whose width is scaled by the
            # key's total count relative to the largest key. It sits inside
            # a fixed-width "bar area" so the total label lands in the same
            # column regardless of each key's magnitude.
            bar = Horizontal(*segments, classes="tag-summary-bar-stack")
            bar.styles.width = f"{total / max_total * 100:.2f}%"
            bar_area = Horizontal(bar, classes="tag-summary-bar-area")

            key_label = Static(key, classes="tag-summary-key")
            key_label.styles.width = key_width

            row = Horizontal(
                key_label,
                bar_area,
                Static(str(total), classes="tag-summary-total"),
                classes="tag-summary-row",
            )

            scroll.mount(row)

    def show_error(self, message: str) -> None:
        """Display an error message."""
        self.remove_children()
        self.mount(Static(message, classes="detail-error"))

    def show_placeholder(self) -> None:
        """Show the default placeholder."""
        self.remove_children()
        self.mount(Static("Select a resource to view details"))
