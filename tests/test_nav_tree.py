from unittest.mock import MagicMock

from rich.style import Style

from awstui.widgets.nav_tree import AWSNavTree, _size_bar_cells


def _tree():
    return AWSNavTree(MagicMock(), [])


def test_size_bar_cells_rounding_and_clamp():
    assert _size_bar_cells(0.0, 20) == 0
    assert _size_bar_cells(1.0, 20) == 20
    assert _size_bar_cells(0.5, 20) == 10
    assert _size_bar_cells(0.69, 16) == 11  # round(11.04)
    assert _size_bar_cells(0.125, 20) == 2  # round(2.5) -> 2 (banker's rounding)
    # Clamp out-of-range inputs.
    assert _size_bar_cells(-0.5, 20) == 0
    assert _size_bar_cells(1.5, 20) == 20
    # Non-positive width -> no bar.
    assert _size_bar_cells(0.5, 0) == 0
    assert _size_bar_cells(0.5, -3) == 0


class _FakeTN:
    """Stand-in for a Textual TreeNode (has .parent)."""

    def __init__(self, parent=None):
        self.parent = parent


def test_size_fraction_own_over_parent():
    tree = _tree()
    parent = _FakeTN()
    child = _FakeTN(parent=parent)
    tree.size_values = {id(parent): 1000, id(child): 690}
    assert tree._size_fraction(child) == 0.69


def test_size_fraction_none_when_parent_unsized():
    tree = _tree()
    parent = _FakeTN()
    child = _FakeTN(parent=parent)
    tree.size_values = {id(child): 690}  # parent missing
    assert tree._size_fraction(child) is None


def test_size_fraction_none_when_own_unsized():
    tree = _tree()
    parent = _FakeTN()
    child = _FakeTN(parent=parent)
    tree.size_values = {id(parent): 1000}  # child missing
    assert tree._size_fraction(child) is None


def test_size_fraction_none_when_parent_total_zero():
    tree = _tree()
    parent = _FakeTN()
    child = _FakeTN(parent=parent)
    tree.size_values = {id(parent): 0, id(child): 0}
    assert tree._size_fraction(child) is None


def test_size_fraction_none_when_no_parent():
    tree = _tree()
    root = _FakeTN(parent=None)
    tree.size_values = {id(root): 500}
    assert tree._size_fraction(root) is None


def test_node_depth_counts_ancestors():
    tree = _tree()
    root = _FakeTN()
    a = _FakeTN(parent=root)
    b = _FakeTN(parent=a)
    assert tree._node_depth(root) == 0
    assert tree._node_depth(a) == 1
    assert tree._node_depth(b) == 2


def _bg_span_len(text):
    """Total cells covered by spans that set a background colour."""
    return sum(
        (span.end - span.start)
        for span in text.spans
        if isinstance(span.style, Style) and span.style.bgcolor is not None
    )


def test_render_label_paints_bar_for_sized_node(monkeypatch):
    tree = _tree()
    parent = tree.root.add("bucket")
    child = parent.add("logs/")
    tree.size_values = {id(parent): 1000, id(child): 500}  # 50%
    # Fixed available width so the test is mount-independent.
    monkeypatch.setattr(tree, "_available_bar_width", lambda node: 20)

    text = tree.render_label(child, Style(), Style())

    # 50% of 20 = 10 cells shaded; label padded only to the bar length (10),
    # not the full available width (20), to avoid inflating the tree's
    # measured label/virtual width.
    assert _bg_span_len(text) == 10
    assert text.cell_len == 10


def test_render_label_no_bar_when_unsized(monkeypatch):
    tree = _tree()
    parent = tree.root.add("bucket")
    child = parent.add("logs/")
    # Nothing in size_values -> fraction None.
    monkeypatch.setattr(tree, "_available_bar_width", lambda node: 20)

    text = tree.render_label(child, Style(), Style())
    assert _bg_span_len(text) == 0


def test_render_label_no_bar_when_width_zero(monkeypatch):
    tree = _tree()
    parent = tree.root.add("bucket")
    child = parent.add("logs/")
    tree.size_values = {id(parent): 1000, id(child): 500}
    monkeypatch.setattr(tree, "_available_bar_width", lambda node: 0)

    text = tree.render_label(child, Style(), Style())
    assert _bg_span_len(text) == 0


def test_render_label_no_bar_when_fraction_rounds_to_zero(monkeypatch):
    tree = _tree()
    parent = tree.root.add("bucket")
    child = parent.add("logs/")
    # 10/1000 = 1% of 20 cells -> round(0.2) -> 0 cells -> no bar.
    tree.size_values = {id(parent): 1000, id(child): 10}
    monkeypatch.setattr(tree, "_available_bar_width", lambda node: 20)

    text = tree.render_label(child, Style(), Style())
    assert _bg_span_len(text) == 0
