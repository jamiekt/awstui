"""Unit tests for AWSNavTree.filter_children.

These test the filter bookkeeping (snapshot/restore + case-insensitive
substring match) without standing up a real Textual app — we fake the
TreeNode-like parent object that Textual's Tree exposes.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from awstui.models import TreeNode
from awstui.widgets.nav_tree import AWSNavTree


def make_tree_node(label: str) -> TreeNode:
    return TreeNode(
        id=f"n:{label}",
        label=label,
        node_type="item",
        service="fake",
        expandable=False,
        metadata={},
    )


def make_parent(labels: list[str], parent_label: str = "Buckets"):
    """Build a fake Textual tree-node parent with the given child labels."""
    parent = MagicMock()
    parent.is_expanded = True
    parent.label = parent_label

    def set_label(new_label):
        parent.label = new_label

    parent.set_label.side_effect = set_label

    children = []
    added: list[tuple[str, TreeNode]] = []

    def add(label, data=None):
        child = MagicMock()
        child.label = label
        child.data = data
        child.allow_expand = False
        children.append(child)
        added.append((str(label), data))
        return child

    def remove_children():
        children.clear()

    parent.children = children
    parent.add.side_effect = add
    parent.remove_children.side_effect = remove_children
    # Populate the initial children via add()
    for label in labels:
        add(label, data=make_tree_node(label))
    # Reset the counter so test assertions can check post-init calls.
    parent.add.reset_mock()
    parent.remove_children.reset_mock()
    parent._added = added  # for inspection in tests
    return parent


def new_tree() -> AWSNavTree:
    tree = AWSNavTree.__new__(AWSNavTree)
    tree._unfiltered_children = {}
    tree._original_labels = {}
    return tree


def test_filter_keeps_matching_children():
    tree = new_tree()
    parent = make_parent(["alpha-bucket", "beta-bucket", "gamma-log"])

    count = tree.filter_children(parent, "bucket")

    assert count == 2
    kept_labels = [label for label, _ in parent._added[-2:]]
    assert kept_labels == ["alpha-bucket", "beta-bucket"]


def test_filter_is_case_insensitive():
    tree = new_tree()
    parent = make_parent(["MyBucket", "OtherThing", "my-file"])

    count = tree.filter_children(parent, "MY")

    assert count == 2


def test_empty_filter_restores_all_children():
    tree = new_tree()
    parent = make_parent(["a", "bucket-b", "c"])

    tree.filter_children(parent, "b")
    # Parent now only has children whose label contains 'b'.
    kept_labels = [str(c.label) for c in parent.children]
    assert kept_labels == ["bucket-b"]

    # Clearing restores all originals.
    tree.filter_children(parent, "")
    restored_labels = [str(c.label) for c in parent.children]
    assert restored_labels == ["a", "bucket-b", "c"]


def test_filter_twice_uses_original_snapshot():
    """A second filter compares against the originals, not the first result."""
    tree = new_tree()
    parent = make_parent(["apple", "banana", "apricot"])

    tree.filter_children(parent, "ap")
    # First filter keeps apple, apricot.
    assert [str(c.label) for c in parent.children] == ["apple", "apricot"]

    tree.filter_children(parent, "banana")
    # banana should reappear even though it was filtered out first.
    assert [str(c.label) for c in parent.children] == ["banana"]


def test_filter_returns_zero_when_no_matches():
    tree = new_tree()
    parent = make_parent(["alpha", "beta"])

    count = tree.filter_children(parent, "zzz")

    assert count == 0
    assert parent.children == []


def test_clearing_drops_snapshot():
    tree = new_tree()
    parent = make_parent(["x", "y"])

    tree.filter_children(parent, "x")
    assert id(parent) in tree._unfiltered_children

    tree.filter_children(parent, "")
    assert id(parent) not in tree._unfiltered_children


def test_filter_sets_badge_on_parent_label():
    tree = new_tree()
    parent = make_parent(["alpha-bucket", "beta-bucket"], parent_label="Buckets")

    tree.filter_children(parent, "alpha")

    # parent.label is now a Rich Text carrying the original label + badge.
    rendered = str(parent.label)
    assert rendered.startswith("Buckets")
    assert "alpha" in rendered
    # The badge uses the 🔍 icon.
    assert "🔍" in rendered


def test_clearing_filter_restores_parent_label():
    tree = new_tree()
    parent = make_parent(["a", "b"], parent_label="My Section")

    tree.filter_children(parent, "a")
    assert "🔍" in str(parent.label)

    tree.filter_children(parent, "")
    assert str(parent.label) == "My Section"
    # And the tracking dict is cleared too.
    assert id(parent) not in tree._original_labels


def test_filter_twice_updates_badge_to_new_substring():
    tree = new_tree()
    parent = make_parent(["apple", "apricot", "banana"], parent_label="Fruit")

    tree.filter_children(parent, "ap")
    assert "ap" in str(parent.label)

    tree.filter_children(parent, "banana")
    rendered = str(parent.label)
    assert "banana" in rendered
    assert " ap)" not in rendered  # the old substring is gone
