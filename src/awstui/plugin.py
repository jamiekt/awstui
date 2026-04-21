from __future__ import annotations

from abc import ABC, abstractmethod

import boto3

from awstui.models import ResourceDetails, TreeNode


class AWSServicePlugin(ABC):
    """Base class for all AWS service plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Display name, e.g. 'S3', 'Lambda'."""

    @property
    @abstractmethod
    def service_name(self) -> str:
        """boto3 service name, e.g. 's3', 'lambda'."""

    @property
    def has_flat_root(self) -> bool:
        """True if get_root_nodes returns resource nodes directly.

        False for services that expose intermediate category nodes
        (e.g. IAM has Users/Roles/Policies/Groups; RDS has DB
        Instances/DB Clusters). Used to decide whether a count can
        be shown when the service root is selected.
        """
        return True

    @abstractmethod
    def get_root_nodes(self, session: boto3.Session) -> list[TreeNode]:
        """Return top-level resource nodes for this service."""

    @abstractmethod
    def get_children(self, session: boto3.Session, node: TreeNode) -> list[TreeNode]:
        """Return child nodes for the given node."""

    @abstractmethod
    def get_details(self, session: boto3.Session, node: TreeNode) -> ResourceDetails:
        """Return details for the given node."""


class PluginRegistry:
    """Registry for discovered service plugins."""

    def __init__(self):
        self._plugins: dict[str, AWSServicePlugin] = {}

    def register(self, plugin: AWSServicePlugin) -> None:
        self._plugins[plugin.service_name] = plugin

    def get(self, service_name: str) -> AWSServicePlugin | None:
        return self._plugins.get(service_name)

    def list_plugins(self) -> list[AWSServicePlugin]:
        return list(self._plugins.values())
