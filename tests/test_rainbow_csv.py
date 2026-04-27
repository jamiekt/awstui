from awstui.models import ContentPreview
from awstui.widgets.detail_pane import (
    DetailPane,
    _RAINBOW_CSV_COLORS,
    _render_rainbow_csv,
)


def _spans(text) -> list[tuple[str, str]]:
    """Return (plain_text_slice, style) pairs for each span in the Text."""
    plain = text.plain
    return [(plain[s.start : s.end], str(s.style)) for s in text.spans]


def test_rainbow_csv_colors_columns_with_cycled_palette():
    rendered = _render_rainbow_csv("a,b,c\n1,2,3")

    # Plain text should be exactly the input, delimiters preserved.
    assert rendered.plain == "a,b,c\n1,2,3"

    # Each non-delimiter field is styled with the colour for its column index.
    styles = [
        style for (_slice, style) in _spans(rendered) if _slice not in (",", "\n")
    ]
    # 2 rows * 3 columns = 6 styled fields.
    assert len(styles) == 6
    expected = [_RAINBOW_CSV_COLORS[i % len(_RAINBOW_CSV_COLORS)] for i in range(3)] * 2
    assert styles == expected


def test_rainbow_csv_handles_quoted_fields_with_commas():
    # Middle field contains a comma inside quotes — the csv module should
    # treat it as one field, so the second column styling wraps the full
    # quoted string.
    rendered = _render_rainbow_csv('name,"Doe, John",age\n"Smith, Jane","x,y",42')
    # The raw bytes of commas/newlines are preserved verbatim.
    assert rendered.plain.count("\n") == 1
    # Header still resolves to 3 columns -> 3 styled spans on row 1.
    row1_styles = [
        style
        for slice_, style in _spans(rendered)
        if "\n" not in slice_ and slice_ != "," and slice_
    ]
    # 3 fields per row, 2 rows => 6 styled spans.
    assert len(row1_styles) == 6


def test_rainbow_csv_auto_detects_tab_delimiter():
    rendered = _render_rainbow_csv("a\tb\tc\n1\t2\t3")
    assert "\t" in rendered.plain
    assert rendered.plain == "a\tb\tc\n1\t2\t3"


def test_rainbow_csv_empty_input():
    rendered = _render_rainbow_csv("")
    assert rendered.plain == ""


def test_csv_defaults_to_no_wrap_other_languages_to_wrap():
    # We don't mount the DetailPane into an app; we just exercise the
    # pure-state update in set_content_preview / toggle_content_wrap.
    pane = DetailPane.__new__(DetailPane)
    pane._content_preview = None
    pane._content_wrap = True

    # Bypass the rendering side-effect by overriding _render_content.
    pane._render_content = lambda: None  # type: ignore[method-assign]

    csv_preview = ContentPreview(kind="text", body="a,b\n1,2", language="csv")
    pane.set_content_preview(csv_preview)
    assert pane._content_wrap is False  # CSV defaults to no-wrap

    py_preview = ContentPreview(kind="text", body="print(1)", language="python")
    pane.set_content_preview(py_preview)
    assert pane._content_wrap is True  # non-CSV defaults to wrap


def test_toggle_content_wrap_flips_state():
    pane = DetailPane.__new__(DetailPane)
    pane._content_preview = ContentPreview(kind="text", body="x", language="python")
    pane._content_wrap = True
    pane._render_content = lambda: None  # type: ignore[method-assign]

    assert pane.toggle_content_wrap() is False
    assert pane._content_wrap is False
    assert pane.toggle_content_wrap() is True
    assert pane._content_wrap is True
