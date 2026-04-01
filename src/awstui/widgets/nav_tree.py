from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import ClientError
from textual.message import Message
from textual.widgets import Tree
from textual.widgets._tree import TreeNode as TextualTreeNode

from awstui.models import TreeNode
from awstui.plugin import AWSServicePlugin


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

    def __init__(self, session: boto3.Session, plugins: list[AWSServicePlugin]) -> None:
        super().__init__("AWS Services")
        self._session = session
        self._plugins: dict[str, AWSServicePlugin] = {p.service_name: p for p in plugins}

    @property
    def session(self) -> boto3.Session:
        return self._session

    @session.setter
    def session(self, value: boto3.Session) -> None:
        self._session = value

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
            if error_code in ("AccessDenied", "AccessDeniedException", "UnauthorizedAccess"):
                self.post_message(NodeError(f"Access Denied: insufficient permissions to list {data.label}"))
            else:
                self.post_message(NodeError(f"Error loading {data.label}: {e}"))
        except Exception as e:
            self.post_message(NodeError(f"Error loading {data.label}: {e}"))

    def on_tree_node_selected(self, event: Tree.NodeSelected[TreeNode]) -> None:
        if event.node.data is not None:
            self.post_message(NodeSelected(event.node.data))

    def reset_tree(self) -> None:
        """Clear and repopulate the tree (e.g. after region switch)."""
        self.clear()
        self._populate_services()
