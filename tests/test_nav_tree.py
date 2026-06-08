from unittest.mock import MagicMock

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
