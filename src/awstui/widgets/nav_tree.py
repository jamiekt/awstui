from __future__ import annotations

import boto3
from botocore.exceptions import ClientError
from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Tree

from awstui.models import TreeNode
from awstui.plugin import AWSServicePlugin

# Shown next to a node's label when a filter is active on its children.
_FILTER_BADGE_COLOR = "bright_yellow"
_FILTER_ICON = "🔍"


def _size_bar_cells(fraction: float, width: int) -> int:
    """Number of cells to shade for a bar of `fraction` over `width` cells.

    Clamps `fraction` to [0, 1] and the result to [0, width]; returns 0 for a
    non-positive width.
    """
    if width <= 0:
        return 0
    fraction = max(0.0, min(1.0, fraction))
    return max(0, min(width, round(fraction * width)))


class NodeSelected(Message):
    """Posted when a tree node is selected."""

    def __init__(self, node_data: TreeNode) -> None:
        super().__init__()
        self.node_data = node_data


class NodeError(Message):
    """Posted when loading a node fails."""

    def __init__(self, error_message: str) -> None:
        super().__init__()
        self.error_message = error_message


class AWSNavTree(Tree[TreeNode]):
    """Navigation tree for browsing AWS resources."""

    BINDINGS = [
        Binding("left", "collapse_or_parent", "Collapse / parent", show=False),
        Binding("right", "expand_or_child", "Expand / child", show=False),
    ]

    def __init__(self, session: boto3.Session, plugins: list[AWSServicePlugin]) -> None:
        super().__init__("AWS Services")
        self._session = session
        self._plugins: dict[str, AWSServicePlugin] = {
            p.service_name: p for p in plugins
        }
        # Snapshot of original (label, data) child pairs keyed by parent node
        # id, captured the first time a filter is applied so clearing the
        # filter can restore the full list without re-fetching from AWS.
        self._unfiltered_children: dict[int, list[tuple[str, TreeNode]]] = {}
        # Original (unfiltered) label for each currently-filtered parent, so
        # we can restore it when the filter is cleared.
        self._original_labels: dict[int, str] = {}
        # id(textual TreeNode) -> byte total, shared by reference from the app
        # (AWSBrowserApp._size_values). Drives the sibling-relative size bar in
        # render_label. Empty until the app wires it up in on_mount.
        self.size_values: dict[int, int] = {}

    @property
    def session(self) -> boto3.Session:
        return self._session

    @session.setter
    def session(self, value: boto3.Session) -> None:
        self._session = value

    def _node_depth(self, node) -> int:
        """Number of ancestors between `node` and the root (root -> 0)."""
        depth = 0
        parent = node.parent
        while parent is not None:
            depth += 1
            parent = parent.parent
        return depth

    def _available_bar_width(self, node) -> int:
        """Cells available for the label region of `node`'s row.

        Equals the tree's content width minus this node's indentation
        (`depth * guide_depth`). 0 (no bar) when unmounted or too narrow.
        """
        return max(0, self.size.width - self._node_depth(node) * self.guide_depth)

    def _size_fraction(self, node) -> float | None:
        """`node`'s byte total as a fraction of its parent's, or None.

        None when the node or its parent has no recorded size, the node has no
        parent, or the parent total is 0.
        """
        own = self.size_values.get(id(node))
        parent = node.parent
        if own is None or parent is None:
            return None
        parent_total = self.size_values.get(id(parent))
        if not parent_total:  # None or 0
            return None
        return own / parent_total

    def on_mount(self) -> None:
        self.root.expand()
        self._populate_services()

    def _populate_services(self) -> None:
        for plugin in self._plugins.values():
            service_node = self.root.add(
                plugin.name,
                data=TreeNode(
                    id=f"service:{plugin.service_name}",
                    label=plugin.name,
                    node_type="service",
                    service=plugin.service_name,
                    expandable=True,
                ),
            )
            service_node.allow_expand = True

    def on_tree_node_expanded(self, event: Tree.NodeExpanded[TreeNode]) -> None:
        node = event.node
        if node.data is None:
            return

        # Only load children if they haven't been loaded yet
        if node.children:
            return

        data: TreeNode = node.data
        plugin = self._plugins.get(data.service)
        if plugin is None:
            return

        try:
            if data.node_type == "service":
                children = plugin.get_root_nodes(self._session)
            else:
                children = plugin.get_children(self._session, data)

            for child in children:
                child_node = node.add(child.label, data=child)
                child_node.allow_expand = child.expandable
        except ClientError as e:
            error_code = e.response["Error"].get("Code", "")
            if error_code in (
                "AccessDenied",
                "AccessDeniedException",
                "UnauthorizedAccess",
            ):
                self.post_message(
                    NodeError(
                        f"Access Denied: insufficient permissions to list {data.label}"
                    )
                )
            else:
                self.post_message(NodeError(f"Error loading {data.label}: {e}"))
        except Exception as e:
            self.post_message(NodeError(f"Error loading {data.label}: {e}"))

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[TreeNode]) -> None:
        if event.node.data is not None:
            self.post_message(NodeSelected(event.node.data))

    def action_collapse_or_parent(self) -> None:
        """Collapse the current node; if already collapsed, move to parent."""
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
            return
        parent = node.parent
        if parent is not None and parent is not self.root:
            self.select_node(parent)
            self.scroll_to_node(parent)

    def action_expand_or_child(self) -> None:
        """Expand the current node; if already expanded, move to first child."""
        node = self.cursor_node
        if node is None or not node.allow_expand:
            return
        if not node.is_expanded:
            node.expand()
            return
        if node.children:
            first = node.children[0]
            self.select_node(first)
            self.scroll_to_node(first)

    def reset_tree(self) -> None:
        """Clear and repopulate the tree (e.g. after region switch)."""
        self.clear()
        self._unfiltered_children.clear()
        self._original_labels.clear()
        self._populate_services()

    def filter_children(self, parent, substring: str) -> int:
        """Show only children of `parent` whose label contains `substring`.

        The first call snapshots the current children so a subsequent empty
        string restores them. Matching is case-insensitive. Returns the
        number of visible children after filtering.

        Also updates the parent node's own label to display a filter badge
        (icon + substring in parentheses) so the filter is visible even
        when the parent is collapsed.
        """
        parent_id = id(parent)
        if parent_id not in self._unfiltered_children:
            self._unfiltered_children[parent_id] = [
                (str(child.label), child.data)
                for child in parent.children
                if child.data is not None
            ]
        if parent_id not in self._original_labels:
            self._original_labels[parent_id] = str(parent.label)

        originals = self._unfiltered_children[parent_id]
        needle = substring.lower()

        parent.remove_children()

        if not needle:
            # Clearing the filter: restore all originals + the plain label.
            self._unfiltered_children.pop(parent_id, None)
            parent.set_label(self._original_labels.pop(parent_id))
            kept = originals
        else:
            kept = [
                (label, data) for label, data in originals if needle in label.lower()
            ]
            parent.set_label(
                _label_with_filter_badge(self._original_labels[parent_id], substring)
            )

        for label, data in kept:
            child_node = parent.add(label, data=data)
            child_node.allow_expand = data.expandable

        if not parent.is_expanded:
            parent.expand()

        return len(kept)


def _label_with_filter_badge(original_label: str, substring: str) -> Text:
    """Compose a parent label with a coloured filter badge appended.

    e.g. "Buckets (🔍 logs)" with the part in parentheses rendered in
    `_FILTER_BADGE_COLOR`.
    """
    label = Text(original_label)
    label.append(f" ({_FILTER_ICON} {substring})", style=_FILTER_BADGE_COLOR)
    return label
