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
from textual.containers import Container, Horizontal
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
        try:
            table = self.query_one("#sql-result", DataTable)
            table.clear(columns=True)
            table.add_column("Error")
            table.add_row(message)
        except Exception:
            pass
        self._set_status("Error")

    def _reset_result(self) -> None:
        try:
            table = self.query_one("#sql-result", DataTable)
            table.clear(columns=True)
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
