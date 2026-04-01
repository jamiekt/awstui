from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TreeNode:
    """Represents a node in the AWS resource navigation tree."""

    id: str
    label: str
    node_type: str
    service: str
    expandable: bool
    metadata: dict = field(default_factory=dict)


@dataclass
class ResourceDetails:
    """Details for display in the detail pane."""

    title: str
    subtitle: str
    summary: dict[str, str]
    raw: dict
