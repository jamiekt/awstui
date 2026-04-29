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
    """Details for display in the detail pane.

    `summary` is the flat top-level section of key/value pairs.

    `summary_groups` is an optional ordered list of collapsible
    sub-sections rendered below the top-level summary. Each group has
    a heading and its own dict of key/value pairs — useful for dense
    child data like Glue columns / partition keys.
    """

    title: str
    subtitle: str
    summary: dict[str, str]
    raw: dict
    summary_groups: list[tuple[str, dict[str, str]]] = field(default_factory=list)


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
