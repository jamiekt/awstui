import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from awstui.widgets.sql_pane import SqlPaneContent


class _Harness(App):
    def compose(self) -> ComposeResult:
        yield SqlPaneContent(initial_query="SELECT 1")


@pytest.mark.asyncio
async def test_set_error_shows_full_multiline_message():
    """A multi-line error must be fully visible, not clipped to one row."""
    app = _Harness()
    async with app.run_test(size=(100, 40)):
        pane = app.query_one(SqlPaneContent)
        message = (
            "Invalid Input Error: Required module 'pytz' failed to import, "
            "due to the following Python exception:\n"
            "ModuleNotFoundError: No module named 'pytz'"
        )
        pane.set_error(message)
        await app.workers.wait_for_complete()

        error_static = pane.query_one("#sql-error", Static)
        rendered = str(error_static.render())
        # Both lines present, in full — including the previously-hidden cause.
        assert "pytz' failed to import" in rendered
        assert "ModuleNotFoundError: No module named 'pytz'" in rendered

        # Error pane visible, result table hidden.
        assert pane.query_one("#sql-error-scroll").display is True
        assert pane.query_one("#sql-result", DataTable).display is False


@pytest.mark.asyncio
async def test_set_result_hides_error_pane():
    """Showing a result hides any previously-shown error."""
    app = _Harness()
    async with app.run_test(size=(100, 40)):
        pane = app.query_one(SqlPaneContent)
        pane.set_error("some error")
        await app.workers.wait_for_complete()
        assert pane.query_one("#sql-error-scroll").display is True

        pane.set_result(["a", "b"], [(1, 2)], truncated=False, total_columns=2)
        await app.workers.wait_for_complete()

        assert pane.query_one("#sql-error-scroll").display is False
        assert pane.query_one("#sql-result", DataTable).display is True
