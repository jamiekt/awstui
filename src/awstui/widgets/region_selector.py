from __future__ import annotations

from textual.message import Message
from textual.widgets import Select


AWS_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "af-south-1",
    "ap-east-1",
    "ap-south-1",
    "ap-south-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-southeast-3",
    "ap-northeast-1",
    "ap-northeast-2",
    "ap-northeast-3",
    "ca-central-1",
    "eu-central-1",
    "eu-central-2",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "eu-south-1",
    "eu-south-2",
    "eu-north-1",
    "il-central-1",
    "me-south-1",
    "me-central-1",
    "sa-east-1",
]


class RegionChanged(Message):
    """Posted when the user selects a new region."""

    def __init__(self, region: str) -> None:
        super().__init__()
        self.region = region


class RegionSelector(Select[str]):
    """Dropdown for selecting an AWS region."""

    def __init__(self, current_region: str) -> None:
        options = [(r, r) for r in AWS_REGIONS]
        super().__init__(options, value=current_region, allow_blank=False)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is not None:
            self.post_message(RegionChanged(str(event.value)))
