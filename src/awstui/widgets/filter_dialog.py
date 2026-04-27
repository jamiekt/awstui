from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class FilterDialog(ModalScreen[str | None]):
    """Modal dialog prompting for a filter substring.

    Dismisses with the typed string when the user presses enter, or with
    None when they press escape.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    DEFAULT_CSS = """
    FilterDialog {
        align: center middle;
    }
    #filter-dialog-box {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #filter-dialog-prompt {
        margin-bottom: 1;
    }
    """

    def __init__(self, initial: str = "") -> None:
        super().__init__()
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical(id="filter-dialog-box"):
            yield Static(
                "Filter children (Enter to apply, empty to clear, Esc to cancel)",
                id="filter-dialog-prompt",
            )
            yield Input(value=self._initial, id="filter-dialog-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)
