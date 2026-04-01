# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run awstui                              # Run the app
uv run pytest tests/ -v                    # Run all tests
uv run pytest tests/test_services/test_s3.py -v   # Run a single test file
uv run pytest tests/test_services/test_s3.py::test_get_root_nodes_returns_buckets -v  # Run a single test
uv sync                                    # Install/sync dependencies
```

## Architecture

awstui is a read-only TUI for browsing AWS resources, built with Textual and boto3.

### Plugin System

The core abstraction is `AWSServicePlugin` (ABC in `plugin.py`). Each AWS service implements this with three methods: `get_root_nodes()`, `get_children()`, and `get_details()`. Plugins live in `src/awstui/services/` and are auto-discovered — any module with a `plugin = MyPlugin()` at module level gets registered automatically via `services/__init__.py`.

To add a new AWS service: create a new file in `services/`, implement the ABC, set `plugin = MyServicePlugin()`. No other registration needed.

### Data Flow

`TreeNode` carries metadata (bucket names, ARNs, etc.) through the tree so child/detail fetches have the context they need. `ResourceDetails` provides both a curated `summary` dict (for the Summary tab) and the full `raw` API response (for the Raw JSON tab).

### Widget Communication

Widgets communicate via Textual messages. `AWSNavTree` posts `NodeSelected` and `NodeError`. `RegionSelector` posts `RegionChanged`. The main `AWSBrowserApp` listens to all of these and coordinates between the nav tree and detail pane.

### Region and Session

A single `boto3.Session` is held on the app. Region switching creates a new session and resets the tree. IAM always uses `us-east-1` regardless of selected region (global service).

### Error Handling

All boto3 calls in `nav_tree.py` and `app.py` are wrapped to catch `ClientError`. Access denied shows an inline message in the detail pane; the user can continue browsing other resources.

### Testing

Service plugins are tested by mocking `boto3.Session` with `MagicMock`. App tests use Textual's async `run_test()` pilot. No real AWS credentials needed for tests.
