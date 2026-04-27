from __future__ import annotations

import csv
import io
import json

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import ProgressBar, Static, TabbedContent, TabPane

from awstui.models import ContentPreview, ResourceDetails

# Rainbow-csv palette: cycle through these column-by-column. Chosen to
# read well on both dark and light terminal backgrounds.
_RAINBOW_CSV_COLORS = (
    "#e06c75",  # red
    "#e5c07b",  # yellow
    "#98c379",  # green
    "#56b6c2",  # cyan
    "#61afef",  # blue
    "#c678dd",  # purple
)


def _render_rainbow_csv(body: str, no_wrap: bool = False) -> Text:
    """Return a Rich Text where each column is coloured from a cycling palette.

    Uses the csv module so quoted fields and embedded delimiters are handled
    correctly. Delimiter is auto-detected between comma and tab based on the
    first line; defaults to comma. When `no_wrap` is True the returned Text
    reports its full width so a scroll container sees overflow instead of
    the renderer soft-wrapping at the viewport.
    """
    first_newline = body.find("\n")
    header = body if first_newline == -1 else body[:first_newline]
    delimiter = "\t" if header.count("\t") > header.count(",") else ","

    output = Text(no_wrap=no_wrap, overflow="ignore" if no_wrap else "fold")
    reader = csv.reader(io.StringIO(body), delimiter=delimiter)
    for row_index, row in enumerate(reader):
        if row_index > 0:
            output.append("\n")
        for col_index, field in enumerate(row):
            if col_index > 0:
                output.append(delimiter)
            color = _RAINBOW_CSV_COLORS[col_index % len(_RAINBOW_CSV_COLORS)]
            output.append(field, style=color)
    return output


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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._content_preview: ContentPreview | None = None
        self._content_wrap: bool = True

    def compose(self) -> ComposeResult:
        yield Static("Select a resource to view details")

    def show_details(
        self,
        details: ResourceDetails,
        empty_summary_status: str = "No summary available",
        include_tag_summary: bool = False,
        include_content: bool = False,
    ) -> None:
        """Display resource details with Summary, Raw JSON, and optional tabs.

        `empty_summary_status` is the text shown in the Summary tab when
        `details.summary` is empty (e.g. "Retrieving count ..." while a
        child-count fetch is in flight).

        `include_tag_summary` adds a "Tag Summary" tab populated via
        `set_tag_summary`.

        `include_content` adds a "Content" tab populated via
        `set_content_preview`.
        """
        self._content_preview = None
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

        if include_content:
            content_pane = TabPane("Content", id="tab-content")
            tabbed.add_pane(content_pane)
            content_pane.mount(
                Static(
                    "Select this tab to load content",
                    classes="content-status",
                )
            )

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

    def set_content_status(self, message: str) -> None:
        """Replace the Content tab body with a status line (e.g. 'Loading ...')."""
        try:
            content_pane = self.query_one("#tab-content", TabPane)
        except Exception:
            return
        for child in list(content_pane.children):
            child.remove()
        content_pane.mount(Static(message, classes="content-status"))

    def set_content_preview(self, preview: ContentPreview) -> None:
        """Render the Content tab from a ContentPreview.

        CSV content defaults to no-wrap (rainbow columns line up better);
        everything else defaults to wrap. `toggle_content_wrap` flips it.
        """
        self._content_preview = preview
        # Default: CSV is most useful without wrap; other text wraps.
        self._content_wrap = preview.language != "csv"
        self._render_content()

    def toggle_content_wrap(self) -> bool:
        """Flip wrap on/off for the Content tab and re-render.

        Returns the new wrap state.
        """
        self._content_wrap = not self._content_wrap
        self._render_content()
        return self._content_wrap

    def _render_content(self) -> None:
        preview = self._content_preview
        if preview is None:
            return
        try:
            content_pane = self.query_one("#tab-content", TabPane)
        except Exception:
            return
        for child in list(content_pane.children):
            child.remove()

        if preview.kind != "text":
            content_pane.mount(Static(preview.body, classes="content-status"))
            return

        body = preview.body
        if preview.truncated and preview.size is not None:
            body = (
                f"-- truncated; showing first {len(preview.body)} of "
                f"{preview.size} bytes --\n" + body
            )

        wrap = self._content_wrap
        if preview.language == "csv":
            inner = Static(_render_rainbow_csv(body, no_wrap=not wrap))
        elif preview.language:
            inner = Static(
                Syntax(
                    body,
                    preview.language,
                    theme="monokai",
                    line_numbers=False,
                    word_wrap=wrap,
                )
            )
        elif not wrap:
            inner = Static(Text(body, no_wrap=True, overflow="ignore"))
        else:
            inner = Static(body)

        content_pane.mount(VerticalScroll(inner))

    def show_error(self, message: str) -> None:
        """Display an error message."""
        self.remove_children()
        self.mount(Static(message, classes="detail-error"))

    def show_placeholder(self) -> None:
        """Show the default placeholder."""
        self.remove_children()
        self.mount(Static("Select a resource to view details"))
