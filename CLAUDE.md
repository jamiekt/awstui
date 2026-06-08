# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run awstui                              # Run the app
uv run awstui --profile my-profile         # Run with a specific AWS profile
uv run awstui --service s3 --service lambda  # Restrict services shown in the tree
uv run pytest tests/ -v                    # Run all tests
uv run pytest tests/test_services/test_s3.py -v                      # Single test file
uv run pytest tests/test_services/test_s3.py::test_get_root_nodes_returns_categories -v # Single test
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

### Async detail loading

`plugin.get_details()` is **not** called on the UI thread. `on_node_selected` shows a "Loading ..." placeholder immediately, then spawns `_load_details` as a thread worker; the result is rendered back on the UI thread via `_apply_details` (or `_apply_details_error`). This keeps arrow-key navigation snappy when a plugin's `get_details` makes several AWS calls per selection (e.g. S3's `get_bucket_location` + `get_bucket_tagging`). The container-count / content / tag-summary / SQL workers are all dispatched from `_apply_details`, not from the selection handler. The `service`-node path stays synchronous since it makes no AWS call.

### Node size calculation

The `s` hotkey toggles recursive size calculation for the highlighted node. The tree label shows the byte total and, for containers (buckets/prefixes), the object count: `name (1.2 GB, 3,402 objects)` (or `name (⋯ 1.2 GB, 1,201 objects)` while still climbing); leaf objects show size only. It is gated by the generic, opt-in plugin seam `supports_size(node)` / `iter_size(session, node)` — `iter_size` is a generator yielding cumulative `(byte_total, item_count, descendants)` triples, one yield per chunk of work (S3 yields once per `list_objects_v2` page). `descendants` maps a descendant node-id → its cumulative `(bytes, count)`; it's optional (leaf nodes yield `{}`) and only the final yield's breakdown need be complete. `_size_suffix` formats the label and suppresses the count for `object` nodes. Only S3 implements it today (bucket / prefix / object); objects read their size from `metadata["size"]` stashed during the children walk, so no AWS call is needed.

The app owns the orchestration: `_size_base_labels` / `_size_workers` (both keyed by `id(textual_node)`) track which nodes are sized. Region switch / tree reset calls `_cancel_all_sizes`. Sizes live on tree labels (not the detail pane), so they are independent of the `_selection_seq` machinery.

**One walk per sizing operation feeds every descendant.** A single bucket/prefix walk already visits every key needed to total every descendant prefix, so S3's `iter_size` aggregates each key into all its intermediate prefixes (keyed by the same `s3:prefix:{bucket}:{p}` node-id `get_children` builds) and emits that breakdown *cumulatively on every page*. Only the **root** sizing node (the one `s` was pressed on) gets a `@work(thread=True, group="size")` worker; the worker checks `get_current_worker().is_cancelled` between pages and calls `_apply_size_progress` per page via `call_from_thread`. `_apply_size_progress` updates the root's label **and** every currently-sized descendant from the same breakdown dict (looked up by `data.id` over `_iter_sized_descendants`), so parent and children climb in lock-step from one data source — at every page `root_total == direct objects + Σ child-prefix totals`. It commits the breakdown to `_size_cache` (awstui node-id → cumulative `(bytes, count)`) only on the final page (`done=True`), so a node expanded *after* the walk finishes reads an authoritative total, never a partial. The whole callback is dropped if the root is no longer in `_size_base_labels` (toggled off / region-switched mid-flight).

`_size_on` has three cases: (1) a **completed-cache hit** applies the cached total immediately with no worker; (2) a **container under an in-flight ancestor walk** (`_has_sizing_ancestor` finds an ancestor in `_size_workers`) registers with a climbing label but spawns no worker — the ancestor's single walk feeds it, so cascading into a sizing bucket costs zero extra `list_objects_v2` calls; (3) otherwise it spawns a walk as the new root. **Objects are the exception to case 2**: a leaf object never appears in a prefix breakdown, so it always keeps its own (instant, metadata-based) worker. Toggling a node off cascades to descendants it turned on (`_size_off` → `_iter_sized_descendants` → `_cancel_size`, which tolerates the no-worker descendants); expanding a sized node cascades sizing to its new children via `on_tree_node_expanded`. `_cancel_all_sizes` clears `_size_cache` along with the worker/label state. Cache entries are session-lifetime and keyed only by bucket+prefix (no region/account/generation token): region switch clears them, but they are **not** invalidated by external mutation of bucket contents within a session — a re-expand after objects change externally serves the stale cached total.

Sizing counts **current object versions only** — the bucket/prefix walk uses `list_objects_v2`, which never enumerates noncurrent versions or delete markers, so totals on versioned buckets can understate the real stored footprint. `object_version` nodes are intentionally not sizeable (`supports_size` excludes them). Switching to all-versions accounting would mean a `list_object_versions` walk instead.

Sized nodes also get a **sibling-relative size bar**: a faint background shade behind the label spanning `node_bytes / parent_bytes` of the row's width, so a child filling most of its parent shows a long bar. The app records each sized node's byte total in `_size_values` (keyed by `id(textual_node)`, lifecycle mirroring `_size_base_labels`) and shares that dict by reference with `AWSNavTree`. `AWSNavTree.render_label` computes the fraction at paint time (own / parent total, from `size_values`) and shades the first `fraction * available_width` cells of the label's *background* only — text glyphs and foreground colours are untouched, so labels stay legible. `available_width` is the row content width minus the node's indentation (`depth * guide_depth`), so bars track resize/pane-grow and are only comparable within a sibling group. The label is padded only to the bar length (not the full row), so a sized node doesn't inflate the tree's measured label/virtual width. No bar shows when the node or its parent is unsized, the parent total is 0, the fraction rounds to 0 cells, or the pane is too narrow. The bar colour is a tunable constant (`_SIZE_BAR_BG`), chosen for dark themes. Like `_size_base_labels` / `_size_workers`, `_size_values` is keyed by `id(textual_node)`, so filtering a parent's children (which removes and re-adds child nodes) orphans the old entries and the recreated children lose their size label / bar until re-sized — a harmless, pre-existing consequence of the `id()` keying.

### Stale-result protection

Async work (detail load, child count, tag summary, content, SQL) uses `_selection_seq` / `_tag_summary_seq` / `_content_seq` / `_sql_seq` counters. Every new selection increments `_selection_seq`; background workers capture it at start and their UI callbacks drop the result if it no longer matches (the user has navigated on). Workers use `@work(thread=True, exclusive=True, group=...)` so a new dispatch supersedes the in-flight one. When adding new background work, follow the same pattern.

### App-level state

`AWSBrowserApp` tracks the currently selected resource via `_current_raw` (the raw boto3 response), `_current_subtitle` (usually an ARN), and `_current_node` (the `TreeNode` itself). These power the `a`/`u`/`r` hotkeys — for example, `action_copy_uri` reads `_current_node.metadata` to build S3 / ECR URIs without calling AWS again. Reset all three together on error and on region change.

The detail pane's active tab is preserved across nav selections — don't force it back to a default tab when rebuilding contents.

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

### SQL pane (DuckDB)

`widgets/sql_pane.py` hosts a query editor + `DataTable` inside the detail pane's `tab-sql` `TabPane`. It posts `SqlSubmit` messages on Ctrl+Enter / Submit; the app runs DuckDB off-thread and calls back via `set_result` / `set_error`. The editor uses `TextArea.code_editor(language="sql")`, which requires the `textual[syntax]` extra.

Errors render in a scrollable, wrapping `Static` (`#sql-error`) shown in place of the result table, not as a one-row `DataTable` cell — a single cell clips multi-line messages and hides the actionable part. `pytz` is a hard dependency: DuckDB imports it lazily to materialise `TIMESTAMP WITH TIME ZONE` values into Python (e.g. S3 Inventory parquet), so without it any query returning a tz-aware timestamp fails at fetch time.

### Specs and plans

Design specs and implementation plans live under `docs/superpowers/specs/` and `docs/superpowers/plans/`. New non-trivial features should follow the same pattern (brainstorming → spec → plan → implementation).
