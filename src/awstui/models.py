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


@dataclass
class ContentPreview:
    """A preview of a resource's content for the Content tab.

    Plugins return one of these from `get_content` when a resource has
    meaningful content to display (e.g. an S3 object, a Lambda function's
    code). Returning `None` from `get_content` suppresses the tab.

    - `kind="text"`: `body` is rendered (optionally with a syntax lexer).
    - `kind="binary"` or `kind="message"`: `body` is shown as plain text,
      typically an explanatory note like "Binary content, 12.3 MB".
    """

    kind: str
    body: str
    language: str | None = None
    size: int | None = None
    truncated: bool = False
