"""Interactive SQL tab content backed by DuckDB.

Lives inside the detail pane's `tab-sql` TabPane. Posts a SqlSubmit
message when the user submits a query (via Submit button or Ctrl+Enter);
the app handles execution off-thread and calls back into this widget with
the result via `set_result` or `set_error`.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Button, DataTable, Static, TextArea


class SqlSubmit(Message):
    """Posted when the user submits the current query."""

    def __init__(self, query: str) -> None:
        super().__init__()
        self.query = query


class SqlPaneContent(Container):
    """The widget tree mounted inside the SQL tab.

    The query editor sits on top, a Submit button + status line in the
    middle, and the result table at the bottom. Ctrl+Enter from inside
    the TextArea also submits.
    """

    DEFAULT_CSS = """
    SqlPaneContent {
        height: 1fr;
        width: 100%;
        layout: vertical;
    }
    SqlPaneContent > TextArea {
        height: 10;
    }
    SqlPaneContent > Horizontal {
        height: 3;
        padding: 0 1;
    }
    SqlPaneContent #sql-status {
        width: 1fr;
        margin-left: 2;
        color: $text-muted;
        content-align: left middle;
    }
    SqlPaneContent > DataTable {
        height: 1fr;
    }
    SqlPaneContent #sql-error-scroll {
        height: 1fr;
        width: 100%;
        display: none;
    }
    SqlPaneContent #sql-error {
        width: 100%;
        padding: 0 1;
        color: $error;
    }
    """

    BINDINGS = [
        Binding("ctrl+j", "submit", "Submit", show=False),
        Binding("ctrl+enter", "submit", "Submit", show=False),
    ]

    def __init__(self, initial_query: str = "") -> None:
        super().__init__()
        self._initial_query: str = initial_query

    def compose(self) -> ComposeResult:
        yield TextArea.code_editor(self._initial_query, id="sql-editor", language="sql")
        with Horizontal():
            yield Button("Submit", id="sql-submit", variant="primary")
            yield Static("", id="sql-status")
        yield DataTable(id="sql-result", zebra_stripes=True)
        # Errors render here instead of the table — a scrollable, wrapping
        # Static so multi-line messages (e.g. DuckDB's "...\nModuleNotFound...")
        # are fully readable. Hidden until set_error is called.
        with VerticalScroll(id="sql-error-scroll"):
            yield Static("", id="sql-error")

    def set_default_query(self, query: str) -> None:
        """Replace the editor contents with `query`. Clears any prior result."""
        self._initial_query = query
        try:
            editor = self.query_one("#sql-editor", TextArea)
            editor.text = query
            self._reset_result()
            self._set_status("")
        except Exception:
            pass

    def set_running(self) -> None:
        self._set_status("Running ...")
        self._reset_result()

    def set_result(
        self,
        columns: list[str],
        rows: list[tuple],
        truncated: bool,
        total_columns: int,
    ) -> None:
        self._show_error_pane(False)
        try:
            table = self.query_one("#sql-result", DataTable)
        except Exception:
            return
        table.clear(columns=True)
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*[_render_cell(v) for v in row])
        parts = [f"{len(rows)} row(s)"]
        if total_columns != len(columns):
            parts.append(f"{len(columns)} of {total_columns} columns shown")
        if truncated:
            parts.append("truncated")
        self._set_status(" · ".join(parts))

    def set_error(self, message: str) -> None:
        # Render the full (possibly multi-line) message in the scrollable
        # Static rather than a one-line DataTable cell, which would clip it.
        try:
            self.query_one("#sql-result", DataTable).clear(columns=True)
        except Exception:
            pass
        try:
            self.query_one("#sql-error", Static).update(message)
        except Exception:
            pass
        self._show_error_pane(True)
        self._set_status("Error")

    def _reset_result(self) -> None:
        self._show_error_pane(False)
        try:
            table = self.query_one("#sql-result", DataTable)
            table.clear(columns=True)
        except Exception:
            pass

    def _show_error_pane(self, show: bool) -> None:
        """Toggle between the result table and the error pane."""
        try:
            self.query_one("#sql-error-scroll").display = show
            self.query_one("#sql-result", DataTable).display = not show
        except Exception:
            pass

    def _set_status(self, message: str) -> None:
        try:
            self.query_one("#sql-status", Static).update(message)
        except Exception:
            pass

    @on(Button.Pressed, "#sql-submit")
    def _on_submit_pressed(self, event: Button.Pressed) -> None:
        self.action_submit()

    def action_submit(self) -> None:
        try:
            query = self.query_one("#sql-editor", TextArea).text
        except Exception:
            return
        self.post_message(SqlSubmit(query))


def _render_cell(value) -> str:
    if value is None:
        return ""
    return str(value)
