from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Static


class TagsPane(Static, can_focus=True):
    """Right-most pane showing tags of the selected resource."""

    DEFAULT_CSS = """
    TagsPane {
        height: 100%;
        padding: 1;
        border-left: solid $primary;
    }
    TagsPane:focus {
        border: tall $accent;
        padding: 0;
    }
    .tags-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .tags-row {
        margin-bottom: 0;
    }
    .tags-empty {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Tags", classes="tags-title")
        yield Static("Select a resource to view tags", classes="tags-empty")

    def show_tags(self, raw: object) -> None:
        """Extract tags from a raw boto3 response and render them."""
        tags = _extract_tags(raw)
        self.remove_children()
        self.mount(Static("Tags", classes="tags-title"))
        if not tags:
            self.mount(Static("No tags", classes="tags-empty"))
            return
        for key, value in sorted(tags.items()):
            self.mount(
                Static(
                    Text.assemble(
                        (f"{key}: ", "bold dim"),
                        (value, ""),
                    ),
                    classes="tags-row",
                )
            )

    def show_placeholder(self) -> None:
        self.remove_children()
        self.mount(Static("Tags", classes="tags-title"))
        self.mount(Static("Select a resource to view tags", classes="tags-empty"))


def extract_tags(raw: object) -> dict[str, str]:
    """Public alias of _extract_tags."""
    return _extract_tags(raw)


def _extract_tags(raw: object) -> dict[str, str]:
    """Find tags in a boto3 response, regardless of shape.

    Handles the common shapes AWS APIs use:
    - {"Tags": [{"Key": "k", "Value": "v"}, ...]}
    - {"Tags": {"k": "v", ...}}
    - {"TagList": [{"Key": "k", "Value": "v"}, ...]}  (RDS)
    - {"TagSet": [{"Key": "k", "Value": "v"}, ...]}   (S3)
    """
    if not isinstance(raw, dict):
        return {}
    for key in ("Tags", "TagList", "TagSet"):
        if key in raw:
            return _normalize_tags(raw[key])
    return {}


def _normalize_tags(value: object) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    if isinstance(value, list):
        result: dict[str, str] = {}
        for item in value:
            if isinstance(item, dict) and "Key" in item:
                result[str(item["Key"])] = str(item.get("Value", ""))
        return result
    return {}
