# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run awstui                              # Run the app
uv run awstui --profile my-profile         # Run with a specific AWS profile
uv run pytest tests/ -v                    # Run all tests
uv run pytest tests/test_services/test_s3.py -v                      # Single test file
uv run pytest tests/test_services/test_s3.py::test_get_root_nodes -v # Single test
uv run ruff format .                       # Format
uv run ruff check . --fix                  # Lint + autofix
uv run mypy src                            # Type-check
uv sync                                    # Install/sync dependencies
```

Pre-commit runs `ruff format`, `ruff check`, and `mypy` — all via `uv run`. Config lives in `pyproject.toml` only (no `pytest.ini` / `ruff.toml`).

## Architecture

awstui is a read-only TUI for browsing AWS resources, built with Textual and boto3.

### Plugin System

The core abstraction is `AWSServicePlugin` (ABC in `plugin.py`). Each service implements `get_root_nodes()`, `get_children()`, and `get_details()`. Plugins live in `src/awstui/services/` and are auto-discovered — any module with a `plugin = MyPlugin()` at module level gets registered via `services/__init__.py`.

To add a new service: create a new file in `services/`, implement the ABC, set `plugin = MyServicePlugin()`. No other registration needed.

### Flat-root vs category plugins

`AWSServicePlugin.has_flat_root` (default `True`) controls whether the service node itself can show a resource count. Plugins that expose category nodes (S3, IAM, RDS, ECR, SNS) override it to `False`. Flat-root plugins (Lambda, SQS, Secrets Manager) return resource nodes directly from `get_root_nodes()`.

### Container-count mechanism

A node is treated as a "container" when its `get_details()` returns `summary={}` but `expandable=True`. For these, `on_node_selected` shows the detail pane with an "Retrieving count ..." placeholder and spawns `_load_child_count` as a thread worker. It calls `get_children` and derives a noun (e.g. "buckets") from the first child's `node_type`. This is how category nodes get their counts without each plugin having to implement one.

### Stale-result protection

Async work (child count, tag summary) uses `_selection_seq` / `_tag_summary_seq` counters. Every new selection increments `_selection_seq`; background workers compare the seq they captured at start against the current one and drop their result if stale. When adding new background work, follow the same pattern.

### App-level state

`AWSBrowserApp` tracks the currently selected resource via `_current_raw` (the raw boto3 response), `_current_subtitle` (usually an ARN), and `_current_node` (the `TreeNode` itself). These power the `a`/`u`/`r` hotkeys — for example, `action_copy_uri` reads `_current_node.metadata` to build S3 / ECR URIs without calling AWS again. Reset all three together on error and on region change.

### Data flow

`TreeNode.metadata` carries context (bucket names, ARNs, repository_uri, etc.) through the tree so child/detail fetches don't need to re-query. When a parent fetches children, propagate any metadata the children will need — e.g. ECR image children inherit `repository_uri` from their repo parent.

### Tags

The `tags_pane` widget extracts tags from the raw response via common keys: `Tags`, `TagList`, `TagSet` (either as list-of-`{Key,Value}` or as flat dicts). Plugins whose boto3 response *doesn't* include tags inline (ECR, some RDS resources) must call `list_tags_for_resource` in `get_details` and inject the result into the raw dict under one of those keys.

### Region and session

A single `boto3.Session` is held on the app, built via `_build_session` which honours `--profile` and the current region. Region switching creates a new session and calls `tree.reset_tree()`. IAM and ECR Public are global — their plugins pin `region_name="us-east-1"` on the client.

### Widget communication

Widgets communicate via Textual messages: `AWSNavTree` posts `NodeSelected` and `NodeError`; `RegionSelector` posts `RegionChanged`. The app's `on_*` handlers route between the nav tree, detail pane, and tags pane.

### Error handling

boto3 calls in `nav_tree.py` and `app.py` catch `ClientError`. Access denied is detected by error code (`AccessDenied`, `AccessDeniedException`, `UnauthorizedAccess`) and shows an inline message; the user can keep browsing.

### Testing

Service plugins are tested by mocking `boto3.Session` with `MagicMock`. Pattern: `session.client.return_value.some_api.return_value = {...}`. When adding an API call to an existing plugin, any test that already stubs `describe_*` must also stub the new call — a `MagicMock` will return another `MagicMock` rather than raising, so forgotten stubs fail silently with weird behaviour downstream. App tests use Textual's async `run_test()` pilot. No real AWS credentials needed.

### Specs and plans

Design specs and implementation plans live under `docs/superpowers/specs/` and `docs/superpowers/plans/`. New non-trivial features should follow the same pattern (brainstorming → spec → plan → implementation).
