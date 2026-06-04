# S3 Node Size Calculation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `s` hotkey that toggles asynchronous, recursive size calculation for the highlighted S3 bucket / prefix / object, showing the running total in the tree-node label.

**Architecture:** A generic, opt-in plugin seam (`supports_size` / `iter_size`) lets any service expose sizing; only S3 implements it now. The app owns the hotkey, per-node state (`id()`-keyed dicts of base labels and workers), and one non-exclusive thread worker per sized node that consumes the plugin's cumulative-total generator and updates the node label per page via `call_from_thread`.

**Tech Stack:** Python 3.10+, Textual (`@work` thread workers, `Tree`), boto3 (`list_objects_v2` paginator), pytest + `unittest.mock`.

**Reference spec:** `docs/superpowers/specs/2026-06-04-s3-node-size-design.md`

---

## File structure

- **Create** `src/awstui/util.py` — shared `human_bytes(n)` formatter (moved out of `s3.py` so both plugin and app use it).
- **Modify** `src/awstui/plugin.py` — add `supports_size` / `iter_size` to the ABC with no-op defaults.
- **Modify** `src/awstui/services/s3.py` — implement `supports_size` / `iter_size`; stash object `Size` into node metadata; import `human_bytes` from `util`.
- **Modify** `src/awstui/app.py` — `s` binding, `check_action` gating, state dicts, size worker, toggle on/off with symmetric cascade, expand cascade, region/reset cleanup.
- **Modify** `CLAUDE.md` and `pyproject.toml` — document the feature, bump version.
- **Create** `tests/test_util.py` — `human_bytes` tests.
- **Modify** `tests/test_plugin.py` — ABC default tests.
- **Modify** `tests/test_services/test_s3.py` — `supports_size` / `iter_size` / metadata-stash tests.
- **Modify** `tests/test_app.py` — suffix formatter, gating, toggle/cascade logic, one pilot integration test.

---

## Task 1: Shared `human_bytes` helper

**Files:**
- Create: `src/awstui/util.py`
- Create: `tests/test_util.py`
- Modify: `src/awstui/services/s3.py:141-147` (remove local `_human_bytes`, import from util), `src/awstui/services/s3.py:599`, `src/awstui/services/s3.py:724`

- [ ] **Step 1: Write the failing test**

Create `tests/test_util.py`:

```python
from awstui.util import human_bytes


def test_human_bytes_bytes():
    assert human_bytes(0) == "0 B"
    assert human_bytes(512) == "512 B"


def test_human_bytes_kilobytes():
    assert human_bytes(1024) == "1.0 KB"
    assert human_bytes(1536) == "1.5 KB"


def test_human_bytes_megabytes():
    assert human_bytes(1024 * 1024) == "1.0 MB"


def test_human_bytes_gigabytes():
    assert human_bytes(1024 ** 3) == "1.0 GB"


def test_human_bytes_terabytes_and_above_clamp_to_tb():
    assert human_bytes(1024 ** 4) == "1.0 TB"
    # Petabyte-scale still reports in TB (no PB unit).
    assert human_bytes(1024 ** 5).endswith(" TB")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_util.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'awstui.util'`

- [ ] **Step 3: Create the util module**

Create `src/awstui/util.py` (logic copied verbatim from the existing `_human_bytes` in `s3.py`, renamed public):

```python
from __future__ import annotations


def human_bytes(n: int) -> str:
    """Format a byte count as a human-readable string (B, KB, ..., TB)."""
    size: float = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{n} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size} B"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_util.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Replace the local helper in s3.py with the import**

In `src/awstui/services/s3.py`, delete the local `_human_bytes` function (currently lines 141-147):

```python
def _human_bytes(n: int) -> str:
    size: float = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{n} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size} B"
```

Add to the imports at the top of `s3.py` (after `from awstui.plugin import AWSServicePlugin`):

```python
from awstui.util import human_bytes
```

Then update the two call sites: change `_human_bytes(size)` (in `_preview_s3_object`) to `human_bytes(size)`, and `_human_bytes(int(size))` (in `_format_version_records`) to `human_bytes(int(size))`.

- [ ] **Step 6: Run the full suite to confirm nothing regressed**

Run: `uv run pytest tests/ -q`
Expected: PASS (all existing tests still green)

- [ ] **Step 7: Format, lint, type-check**

Run: `uv run ruff format . && uv run ruff check . --fix && uv run mypy src`
Expected: all pass, no errors

- [ ] **Step 8: Commit**

```bash
git add src/awstui/util.py tests/test_util.py src/awstui/services/s3.py
git commit -m "$(cat <<'EOF'
refactor: extract human_bytes into awstui.util

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Plugin ABC seam (`supports_size` / `iter_size`)

**Files:**
- Modify: `src/awstui/plugin.py` (add two methods after `default_sql`, ~line 77)
- Modify: `tests/test_plugin.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_plugin.py`:

```python
def test_supports_size_defaults_false():
    from awstui.plugin import AWSServicePlugin
    from awstui.models import TreeNode

    class Dummy(AWSServicePlugin):
        @property
        def name(self):
            return "Dummy"

        @property
        def service_name(self):
            return "dummy"

        def get_root_nodes(self, session):
            return []

        def get_children(self, session, node):
            return []

        def get_details(self, session, node):
            raise NotImplementedError

    node = TreeNode(
        id="x", label="x", node_type="thing", service="dummy", expandable=False
    )
    assert Dummy().supports_size(node) is False


def test_iter_size_default_raises_not_implemented():
    import pytest
    from awstui.plugin import AWSServicePlugin
    from awstui.models import TreeNode

    class Dummy(AWSServicePlugin):
        @property
        def name(self):
            return "Dummy"

        @property
        def service_name(self):
            return "dummy"

        def get_root_nodes(self, session):
            return []

        def get_children(self, session, node):
            return []

        def get_details(self, session, node):
            raise NotImplementedError

    node = TreeNode(
        id="x", label="x", node_type="thing", service="dummy", expandable=False
    )
    with pytest.raises(NotImplementedError):
        Dummy().iter_size(None, node)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plugin.py -k size -v`
Expected: FAIL with `AttributeError: 'Dummy' object has no attribute 'supports_size'`

- [ ] **Step 3: Add the methods to the ABC**

In `src/awstui/plugin.py`, add this import near the top (after `from abc import ABC, abstractmethod`):

```python
from collections.abc import Iterator
```

Add these two methods to `AWSServicePlugin`, immediately after `default_sql` (around line 77):

```python
    def supports_size(self, node: TreeNode) -> bool:
        """Fast, no-AWS check: can this node's total size be calculated?

        The app uses this to decide whether the `s` (size) hotkey applies.
        Must be cheap. Default False — services opt in by overriding.
        """
        return False

    def iter_size(self, session: boto3.Session, node: TreeNode) -> Iterator[int]:
        """Yield the *cumulative* byte total for `node` as it grows.

        One yield per chunk of work (e.g. per page of a listing); the final
        yielded value is the total. Consumers stop iterating to cancel.
        Only called when `supports_size(node)` returned True.
        """
        raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_plugin.py -k size -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Lint + type-check**

Run: `uv run ruff format . && uv run ruff check . --fix && uv run mypy src`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/awstui/plugin.py tests/test_plugin.py
git commit -m "$(cat <<'EOF'
feat: add supports_size / iter_size to plugin ABC

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Stash object `Size` into node metadata

**Files:**
- Modify: `src/awstui/services/s3.py:334-352` (object child build inside `get_children`)
- Modify: `tests/test_services/test_s3.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_services/test_s3.py`:

```python
def test_object_children_store_size_in_metadata():
    session = make_session()
    client = session.client.return_value
    client.get_bucket_versioning.return_value = {"Status": "Suspended"}
    client.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {"Key": "file-a.txt", "Size": 123},
                {"Key": "file-b.txt", "Size": 456},
            ]
        }
    ]

    from awstui.models import TreeNode

    bucket_node = TreeNode(
        id="s3:bucket:b",
        label="b",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "b"},
    )

    plugin = S3Plugin()
    children = plugin.get_children(session, bucket_node)

    objects = [c for c in children if c.node_type == "object"]
    assert objects[0].metadata["size"] == 123
    assert objects[1].metadata["size"] == 456
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_services/test_s3.py::test_object_children_store_size_in_metadata -v`
Expected: FAIL with `KeyError: 'size'`

- [ ] **Step 3: Add `size` to the object child metadata**

In `src/awstui/services/s3.py`, in the object loop inside `get_children` (the `for obj in page.get("Contents", [])` block, ~lines 334-352), add a `"size"` entry to the `metadata` dict so it reads:

```python
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key == prefix:
                    continue
                display = key[len(prefix) :]
                children.append(
                    TreeNode(
                        id=f"s3:object:{bucket}:{key}",
                        label=display,
                        node_type="object",
                        service="s3",
                        expandable=bool(versioning_enabled),
                        metadata={
                            "bucket_name": bucket,
                            "key": key,
                            "size": obj.get("Size"),
                            "versioning_enabled": versioning_enabled,
                        },
                    )
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_services/test_s3.py::test_object_children_store_size_in_metadata -v`
Expected: PASS

- [ ] **Step 5: Run the s3 suite to confirm no regression**

Run: `uv run pytest tests/test_services/test_s3.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/awstui/services/s3.py tests/test_services/test_s3.py
git commit -m "$(cat <<'EOF'
feat: store object Size in S3 object node metadata

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: S3 `supports_size`

**Files:**
- Modify: `src/awstui/services/s3.py` (add `supports_size` method to `S3Plugin`, near `has_sql`)
- Modify: `tests/test_services/test_s3.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_services/test_s3.py`:

```python
def test_supports_size_true_for_bucket_prefix_object():
    from awstui.models import TreeNode

    plugin = S3Plugin()
    for node_type in ("bucket", "prefix", "object"):
        node = TreeNode(
            id="x", label="x", node_type=node_type, service="s3", expandable=True
        )
        assert plugin.supports_size(node) is True


def test_supports_size_false_for_other_node_types():
    from awstui.models import TreeNode

    plugin = S3Plugin()
    for node_type in (
        "category",
        "directory_bucket",
        "table_bucket",
        "vector_bucket",
        "access_point",
        "object_version",
    ):
        node = TreeNode(
            id="x", label="x", node_type=node_type, service="s3", expandable=False
        )
        assert plugin.supports_size(node) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_services/test_s3.py -k supports_size -v`
Expected: FAIL — base-class default returns False, so `test_supports_size_true_*` fails on the bucket assertion.

- [ ] **Step 3: Implement `supports_size`**

In `src/awstui/services/s3.py`, add this method to `S3Plugin` (place it just before `has_sql`):

```python
    def supports_size(self, node: TreeNode) -> bool:
        return node.node_type in ("bucket", "prefix", "object")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_services/test_s3.py -k supports_size -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/awstui/services/s3.py tests/test_services/test_s3.py
git commit -m "$(cat <<'EOF'
feat: S3 supports_size for bucket/prefix/object nodes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: S3 `iter_size` for objects

**Files:**
- Modify: `src/awstui/services/s3.py` (add `iter_size` to `S3Plugin`, after `supports_size`)
- Modify: `tests/test_services/test_s3.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_services/test_s3.py`:

```python
def test_iter_size_object_yields_metadata_size_once():
    from awstui.models import TreeNode

    session = make_session()
    node = TreeNode(
        id="s3:object:b:k",
        label="k",
        node_type="object",
        service="s3",
        expandable=False,
        metadata={"bucket_name": "b", "key": "k", "size": 789},
    )

    plugin = S3Plugin()
    totals = list(plugin.iter_size(session, node))

    assert totals == [789]
    # No listing call for a single object.
    session.client.return_value.get_paginator.assert_not_called()


def test_iter_size_object_missing_size_yields_zero():
    from awstui.models import TreeNode

    session = make_session()
    node = TreeNode(
        id="s3:object:b:k",
        label="k",
        node_type="object",
        service="s3",
        expandable=False,
        metadata={"bucket_name": "b", "key": "k", "size": None},
    )

    plugin = S3Plugin()
    assert list(plugin.iter_size(session, node)) == [0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_services/test_s3.py -k iter_size_object -v`
Expected: FAIL with `NotImplementedError` (base-class default).

- [ ] **Step 3: Implement the object branch of `iter_size`**

In `src/awstui/services/s3.py`, add this method to `S3Plugin` immediately after `supports_size`. Add `from collections.abc import Iterator` to the imports at the top of the file if not already present.

```python
    def iter_size(self, session: boto3.Session, node: TreeNode) -> Iterator[int]:
        if node.node_type == "object":
            yield int(node.metadata.get("size") or 0)
            return
        # bucket / prefix recursive walk added in the next task
        client = session.client("s3")
        bucket = node.metadata["bucket_name"]
        prefix = node.metadata.get("prefix", "")
        paginator = client.get_paginator("list_objects_v2")
        total = 0
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                total += obj.get("Size", 0)
            yield total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_services/test_s3.py -k iter_size_object -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Lint + type-check**

Run: `uv run ruff format . && uv run ruff check . --fix && uv run mypy src`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/awstui/services/s3.py tests/test_services/test_s3.py
git commit -m "$(cat <<'EOF'
feat: S3 iter_size yields object size from metadata

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: S3 `iter_size` recursive bucket/prefix walk

The implementation landed in Task 5 (the bucket/prefix branch is already written). This task adds the tests proving the recursive, per-page cumulative behaviour.

**Files:**
- Modify: `tests/test_services/test_s3.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_services/test_s3.py`:

```python
def test_iter_size_bucket_yields_cumulative_total_per_page():
    from awstui.models import TreeNode

    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "a", "Size": 100}, {"Key": "b", "Size": 200}]},
        {"Contents": [{"Key": "c/d", "Size": 50}]},
    ]

    node = TreeNode(
        id="s3:bucket:b",
        label="b",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "b"},
    )

    plugin = S3Plugin()
    totals = list(plugin.iter_size(session, node))

    # One yield per page; running cumulative total.
    assert totals == [300, 350]


def test_iter_size_prefix_walks_recursively_without_delimiter():
    from awstui.models import TreeNode

    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "logs/2026/a", "Size": 10}]},
    ]

    node = TreeNode(
        id="s3:prefix:b:logs/",
        label="logs/",
        node_type="prefix",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "b", "prefix": "logs/"},
    )

    plugin = S3Plugin()
    totals = list(plugin.iter_size(session, node))

    assert totals == [10]
    # Recursive: paginate called with the prefix and NO Delimiter.
    client.get_paginator.return_value.paginate.assert_called_once_with(
        Bucket="b", Prefix="logs/"
    )


def test_iter_size_empty_bucket_yields_zero():
    from awstui.models import TreeNode

    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [{}]

    node = TreeNode(
        id="s3:bucket:b",
        label="b",
        node_type="bucket",
        service="s3",
        expandable=True,
        metadata={"bucket_name": "b"},
    )

    plugin = S3Plugin()
    assert list(plugin.iter_size(session, node)) == [0]
```

- [ ] **Step 2: Run test to verify it passes (implementation already exists)**

Run: `uv run pytest tests/test_services/test_s3.py -k "iter_size_bucket or iter_size_prefix or iter_size_empty" -v`
Expected: PASS (3 passed). If any fail, fix the bucket/prefix branch added in Task 5 to match — particularly that `paginate` is called with `Bucket=` and `Prefix=` only (no `Delimiter`).

- [ ] **Step 3: Commit**

```bash
git add tests/test_services/test_s3.py
git commit -m "$(cat <<'EOF'
test: S3 iter_size recursive bucket/prefix walk

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: App — size suffix formatter + `s` binding gating

**Files:**
- Modify: `src/awstui/app.py` (module-level helper, `BINDINGS`, `__init__` state, `check_action`, `_size_supported`)
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py`:

```python
def test_size_suffix_in_progress_and_done():
    from awstui.app import _size_suffix

    assert _size_suffix(1024, done=False) == " (⋯ 1.0 KB)"
    assert _size_suffix(1024, done=True) == " (1.0 KB)"


def test_check_action_hides_toggle_size_when_unsupported():
    from awstui.plugin import PluginRegistry
    from awstui.services.s3 import S3Plugin

    app = AWSBrowserApp()
    registry = PluginRegistry()
    registry.register(S3Plugin())
    app._plugin_registry = registry

    # Nothing selected -> hidden.
    assert app.check_action("toggle_size", ()) is False
    # A bucket -> shown.
    app._current_node = _node("bucket", bucket_name="b")
    assert app.check_action("toggle_size", ()) is True
    # A category -> hidden.
    app._current_node = _node("category", category="general_purpose_buckets")
    assert app.check_action("toggle_size", ()) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py -k "size_suffix or toggle_size" -v`
Expected: FAIL with `ImportError: cannot import name '_size_suffix'`

- [ ] **Step 3: Add the formatter, binding, state, and gating**

In `src/awstui/app.py`:

(a) Add this module-level function near `_escape_sql` (after line 42):

```python
def _size_suffix(total: int, done: bool) -> str:
    """Return the label suffix for a node's size, e.g. ' (1.0 KB)' when done
    or ' (⋯ 1.0 KB)' while the running total is still climbing."""
    from awstui.util import human_bytes

    human = human_bytes(total)
    return f" ({human})" if done else f" (⋯ {human})"
```

(b) Add the binding to `BINDINGS` (after the `"r"` copy_raw binding, line 56):

```python
        Binding("s", "toggle_size", "Size"),
```

(c) Add state dicts in `__init__` (after `self._sql_seq: int = -1`, line 115):

```python
        # id(textual TreeNode) -> label without the size suffix
        self._size_base_labels: dict[int, str] = {}
        # id(textual TreeNode) -> its in-flight size worker
        self._size_workers: dict = {}
```

(d) Add the gating branch to `check_action` (before `return True`, ~line 311):

```python
        if action == "toggle_size":
            return bool(
                self._current_node is not None
                and self._size_supported(self._current_node)
            )
```

(e) Add this helper method (place it just before `_load_details`, ~line 441):

```python
    def _size_supported(self, node: TreeNode) -> bool:
        if self._plugin_registry is None:
            return False
        plugin = self._plugin_registry.get(node.service)
        return bool(plugin and plugin.supports_size(node))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_app.py -k "size_suffix or toggle_size" -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Lint + type-check**

Run: `uv run ruff format . && uv run ruff check . --fix && uv run mypy src`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/awstui/app.py tests/test_app.py
git commit -m "$(cat <<'EOF'
feat: add s (size) binding gating and suffix formatter

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: App — size worker, toggle on/off, label updates

**Files:**
- Modify: `src/awstui/app.py` (the `_size_worker`, `_set_node_size`, `_set_node_size_unavailable`, `_size_on`, `_cancel_size`, `_size_off`, `_iter_sized_descendants`, `action_toggle_size` methods)
- Modify: `tests/test_app.py`

This task uses lightweight fake nodes for the toggle/cascade logic (no running app needed), then Task 10 adds an end-to-end pilot test.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py`:

```python
class _FakeNode:
    """Minimal stand-in for a Textual tree node for size-logic tests."""

    def __init__(self, label, data=None, children=None):
        self.label = label
        self.data = data
        self.children = children or []
        self.set_label_calls = []

    def set_label(self, label):
        self.label = label
        self.set_label_calls.append(label)


class _FakeWorker:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


def test_set_node_size_updates_label_from_base():
    app = AWSBrowserApp()
    node = _FakeNode("my-folder/")
    app._size_base_labels[id(node)] = "my-folder/"

    app._set_node_size(node, 2048, done=False)
    assert node.label == "my-folder/ (⋯ 2.0 KB)"

    app._set_node_size(node, 2048, done=True)
    assert node.label == "my-folder/ (2.0 KB)"


def test_set_node_size_noop_after_toggle_off():
    app = AWSBrowserApp()
    node = _FakeNode("my-folder/")
    # Not in _size_base_labels -> treated as toggled off; label untouched.
    app._set_node_size(node, 2048, done=True)
    assert node.label == "my-folder/"


def test_cancel_size_restores_label_and_clears_state():
    app = AWSBrowserApp()
    node = _FakeNode("my-folder/ (⋯ 1.0 KB)")
    worker = _FakeWorker()
    app._size_base_labels[id(node)] = "my-folder/"
    app._size_workers[id(node)] = worker

    app._cancel_size(node)

    assert worker.cancelled is True
    assert node.label == "my-folder/"
    assert id(node) not in app._size_base_labels
    assert id(node) not in app._size_workers


def test_size_off_cascades_to_sized_descendants():
    app = AWSBrowserApp()
    grandchild = _FakeNode("gc")
    child = _FakeNode("c", children=[grandchild])
    parent = _FakeNode("p", children=[child])

    for n in (parent, child, grandchild):
        app._size_base_labels[id(n)] = n.label
        app._size_workers[id(n)] = _FakeWorker()

    app._size_off(parent)

    # All three turned off.
    for n in (parent, child, grandchild):
        assert id(n) not in app._size_base_labels
        assert id(n) not in app._size_workers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py -k "set_node_size or cancel_size or size_off" -v`
Expected: FAIL with `AttributeError: 'AWSBrowserApp' object has no attribute '_set_node_size'`

- [ ] **Step 3: Implement the worker and toggle methods**

In `src/awstui/app.py`, add `get_current_worker` to the textual import (change line 13):

```python
from textual import work
from textual.worker import get_current_worker
```

Add these methods to `AWSBrowserApp` (place them after `_size_supported`, before `_load_details`):

```python
    _SIZE_UNAVAILABLE_SUFFIX = " (size unavailable)"

    def action_toggle_size(self) -> None:
        tree = self.query_one(AWSNavTree)
        node = tree.cursor_node
        if node is None or node.data is None:
            return
        if not self._size_supported(node.data):
            self.notify("Size not available for this node", severity="warning")
            return
        if id(node) in self._size_base_labels:
            self._size_off(node)
        else:
            self._size_on(node)

    def _size_on(self, node) -> None:
        """Start sizing `node`: record its base label and spawn a worker."""
        base = str(node.label)
        self._size_base_labels[id(node)] = base
        node.set_label(base + " (⋯)")
        self._size_workers[id(node)] = self._size_worker(node, node.data)

    def _size_off(self, node) -> None:
        """Stop sizing `node` and every descendant it cascaded to."""
        for descendant in list(self._iter_sized_descendants(node)):
            self._cancel_size(descendant)
        self._cancel_size(node)

    def _cancel_size(self, node) -> None:
        worker = self._size_workers.pop(id(node), None)
        if worker is not None:
            worker.cancel()
        base = self._size_base_labels.pop(id(node), None)
        if base is not None:
            node.set_label(base)

    def _iter_sized_descendants(self, node):
        """Yield textual descendants of `node` that are currently sized."""
        for child in getattr(node, "children", []):
            if id(child) in self._size_base_labels:
                yield child
            yield from self._iter_sized_descendants(child)

    def _set_node_size(self, node, total: int, done: bool) -> None:
        base = self._size_base_labels.get(id(node))
        if base is None:
            # Toggled off (or region-switched) while the walk was in flight.
            return
        node.set_label(base + _size_suffix(total, done))

    def _set_node_size_unavailable(self, node) -> None:
        base = self._size_base_labels.get(id(node))
        if base is None:
            return
        node.set_label(base + self._SIZE_UNAVAILABLE_SUFFIX)

    @work(thread=True, group="size")
    def _size_worker(self, node, data: TreeNode) -> None:
        plugin = (
            self._plugin_registry.get(data.service) if self._plugin_registry else None
        )
        if plugin is None or self._session is None:
            return
        worker = get_current_worker()
        total = 0
        try:
            for total in plugin.iter_size(self._session, data):
                if worker.is_cancelled:
                    return
                self.call_from_thread(self._set_node_size, node, total, False)
            self.call_from_thread(self._set_node_size, node, total, True)
        except ClientError:
            self.call_from_thread(self._set_node_size_unavailable, node)
        except Exception:
            self.call_from_thread(self._set_node_size_unavailable, node)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_app.py -k "set_node_size or cancel_size or size_off" -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Lint + type-check**

Run: `uv run ruff format . && uv run ruff check . --fix && uv run mypy src`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/awstui/app.py tests/test_app.py
git commit -m "$(cat <<'EOF'
feat: size worker with toggle on/off and symmetric cascade

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: App — expand cascade

**Files:**
- Modify: `src/awstui/app.py` (`on_tree_node_expanded` handler)
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py`:

```python
def test_expand_cascade_sizes_supported_children(monkeypatch):
    from awstui.plugin import PluginRegistry
    from awstui.services.s3 import S3Plugin

    app = AWSBrowserApp()
    registry = PluginRegistry()
    registry.register(S3Plugin())
    app._plugin_registry = registry

    # Record _size_on calls instead of spawning real workers.
    started = []
    monkeypatch.setattr(app, "_size_on", lambda node: started.append(node))

    prefix_data = _node("prefix", bucket_name="b", prefix="logs/")
    object_data = _node("object", bucket_name="b", key="logs/a", size=1)
    version_data = _node("object_version", bucket_name="b", key="logs/a")

    child_prefix = _FakeNode("logs/", data=prefix_data)
    child_object = _FakeNode("a", data=object_data)
    child_version = _FakeNode("v1", data=version_data)  # unsupported
    parent = _FakeNode(
        "b", data=_node("bucket", bucket_name="b"),
        children=[child_prefix, child_object, child_version],
    )
    # Parent is currently sized.
    app._size_base_labels[id(parent)] = "b"

    class _Event:
        node = parent

    app.on_tree_node_expanded(_Event())

    # Supported children cascade; the object_version child does not.
    assert child_prefix in started
    assert child_object in started
    assert child_version not in started


def test_expand_cascade_noop_when_parent_not_sized(monkeypatch):
    app = AWSBrowserApp()
    started = []
    monkeypatch.setattr(app, "_size_on", lambda node: started.append(node))

    parent = _FakeNode("b", children=[_FakeNode("c", data=_node("prefix"))])

    class _Event:
        node = parent

    app.on_tree_node_expanded(_Event())
    assert started == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py -k expand_cascade -v`
Expected: FAIL with `AttributeError: 'AWSBrowserApp' object has no attribute 'on_tree_node_expanded'`

- [ ] **Step 3: Implement the cascade handler**

In `src/awstui/app.py`, add this handler to `AWSBrowserApp` (place it near `on_node_selected`, e.g. after `on_node_error`, ~line 246):

```python
    def on_tree_node_expanded(self, event) -> None:
        """When a sized node is expanded, cascade sizing to its children.

        Bubbles up after AWSNavTree.on_tree_node_expanded has synchronously
        added the children, so they are present here. Each child that is
        sizeable and not already sized gets turned on.
        """
        node = event.node
        if id(node) not in self._size_base_labels:
            return
        for child in node.children:
            if id(child) in self._size_base_labels:
                continue
            data = getattr(child, "data", None)
            if data is None or not self._size_supported(data):
                continue
            self._size_on(child)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_app.py -k expand_cascade -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Lint + type-check**

Run: `uv run ruff format . && uv run ruff check . --fix && uv run mypy src`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/awstui/app.py tests/test_app.py
git commit -m "$(cat <<'EOF'
feat: cascade size calculation to children on expand

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: App — region/reset cleanup + end-to-end pilot test

**Files:**
- Modify: `src/awstui/app.py` (`_cancel_all_sizes`, call it in `on_region_changed`)
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing unit test for cleanup**

Add to `tests/test_app.py`:

```python
def test_cancel_all_sizes_clears_workers_and_labels():
    app = AWSBrowserApp()
    n1 = _FakeNode("a")
    n2 = _FakeNode("b")
    w1, w2 = _FakeWorker(), _FakeWorker()
    app._size_base_labels[id(n1)] = "a"
    app._size_base_labels[id(n2)] = "b"
    app._size_workers[id(n1)] = w1
    app._size_workers[id(n2)] = w2

    app._cancel_all_sizes()

    assert w1.cancelled and w2.cancelled
    assert app._size_base_labels == {}
    assert app._size_workers == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py -k cancel_all_sizes -v`
Expected: FAIL with `AttributeError: ... '_cancel_all_sizes'`

- [ ] **Step 3: Implement cleanup and wire it into region change**

In `src/awstui/app.py`, add this method (after `_size_off`):

```python
    def _cancel_all_sizes(self) -> None:
        """Cancel every in-flight size walk and forget all size state.

        Called on region switch / tree reset — computed sizes are
        meaningless against a new session, and the tree nodes are gone.
        """
        for worker in self._size_workers.values():
            worker.cancel()
        self._size_workers.clear()
        self._size_base_labels.clear()
```

In `on_region_changed`, add the call alongside the other reset logic (after `self._current_container_node = None`, before `self.refresh_bindings()`):

```python
        self._cancel_all_sizes()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_app.py -k cancel_all_sizes -v`
Expected: PASS

- [ ] **Step 5: Write the end-to-end pilot test**

Add to `tests/test_app.py`:

```python
@pytest.mark.asyncio
async def test_pressing_s_shows_size_in_label_end_to_end():
    """Press `s` on a bucket node and confirm the label gains a size."""
    from awstui.models import TreeNode
    from awstui.plugin import AWSServicePlugin
    from awstui.widgets.nav_tree import AWSNavTree

    class FakeSizePlugin(AWSServicePlugin):
        @property
        def name(self):
            return "Fake"

        @property
        def service_name(self):
            return "fake"

        def get_root_nodes(self, session):
            return [
                TreeNode(
                    id="fake:bucket:b",
                    label="b",
                    node_type="bucket",
                    service="fake",
                    expandable=False,
                    metadata={"bucket_name": "b"},
                )
            ]

        def get_children(self, session, node):
            return []

        def get_details(self, session, node):
            from awstui.models import ResourceDetails

            return ResourceDetails(
                title="b", subtitle="s3://b", summary={"Name": "b"}, raw={}
            )

        def supports_size(self, node):
            return node.node_type == "bucket"

        def iter_size(self, session, node):
            yield 500
            yield 1024

    with patch("awstui.app.boto3") as mock_boto3:
        mock_session = MagicMock()
        mock_session.region_name = "us-east-1"
        mock_boto3.Session.return_value = mock_session

        app = AWSBrowserApp()
        async with app.run_test(size=(120, 40)) as pilot:
            # Replace discovered plugins with our fake, rebuild the tree.
            from awstui.plugin import PluginRegistry

            registry = PluginRegistry()
            registry.register(FakeSizePlugin())
            app._plugin_registry = registry

            tree = app.query_one(AWSNavTree)
            tree._plugins = {"fake": FakeSizePlugin()}
            tree.reset_tree()
            await pilot.pause()

            # Expand the service node to reveal the bucket, select it.
            service_node = tree.root.children[0]
            service_node.expand()
            await pilot.pause()
            bucket_node = service_node.children[0]
            tree.select_node(bucket_node)
            await pilot.pause()

            await pilot.press("s")
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert "1.0 KB" in str(bucket_node.label)
```

- [ ] **Step 6: Run the pilot test**

Run: `uv run pytest tests/test_app.py::test_pressing_s_shows_size_in_label_end_to_end -v`
Expected: PASS. If it is flaky on timing, add one more `await pilot.pause()` after `wait_for_complete()`.

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: PASS (all green)

- [ ] **Step 8: Lint + type-check**

Run: `uv run ruff format . && uv run ruff check . --fix && uv run mypy src`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add src/awstui/app.py tests/test_app.py
git commit -m "$(cat <<'EOF'
feat: cancel size walks on region change; add e2e size test

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Docs + version bump

**Files:**
- Modify: `CLAUDE.md` (Architecture section)
- Modify: `pyproject.toml:3`

- [ ] **Step 1: Bump the version**

In `pyproject.toml`, change line 3 from:

```toml
version = "0.19"
```

to:

```toml
version = "0.20"
```

- [ ] **Step 2: Document the feature in CLAUDE.md**

In `CLAUDE.md`, add a new subsection under `## Architecture` (place it after the "### Async detail loading" section):

```markdown
### Node size calculation

The `s` hotkey toggles recursive size calculation for the highlighted
node, shown in its tree label as `name (1.2 GB)` (or `name (⋯ 1.2 GB)`
while still climbing). It is gated by the generic, opt-in plugin seam
`supports_size(node)` / `iter_size(session, node)` — `iter_size` is a
generator yielding the cumulative byte total, one yield per chunk of
work (S3 yields once per `list_objects_v2` page). Only S3 implements it
today (bucket / prefix / object); objects read their size from
`metadata["size"]` stashed during the children walk, so no AWS call is
needed.

The app owns the orchestration: `_size_base_labels` / `_size_workers`
(both keyed by `id(textual_node)`) track which nodes are sized, one
non-exclusive `@work(thread=True, group="size")` worker per node updates
the label via `call_from_thread`, and the worker checks
`get_current_worker().is_cancelled` between yields. Toggling a node off
cascades to descendants it turned on; expanding a sized node cascades
sizing to its new children. Region switch / tree reset calls
`_cancel_all_sizes`. Sizes live on tree labels (not the detail pane), so
they are independent of the `_selection_seq` machinery.
```

- [ ] **Step 3: Run the full suite + checks (version bump regenerates uv.lock via mypy hook)**

Run: `uv run pytest tests/ -q && uv run ruff format . && uv run ruff check . && uv run mypy src`
Expected: all pass

- [ ] **Step 4: Commit (include uv.lock if the mypy hook regenerated it)**

```bash
git add CLAUDE.md pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
docs: document node size calculation; bump version to 0.20

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

If the commit aborts because the mypy pre-commit hook regenerated `uv.lock`, run `git add uv.lock` and re-run the same commit command.

---

## Self-review notes

- **Spec coverage:** generic seam → Task 2; S3 `supports_size` → Task 4; `iter_size` object → Task 5; recursive bucket/prefix per-page → Tasks 5–6; object metadata stash → Task 3; `human_bytes` move → Task 1; `s` binding + gating → Task 7; worker + label format (`⋯`/done) → Task 8; toggle on/off + symmetric cascade → Task 8; expand cascade (incl. re-expansion via "not already sized") → Task 9; `(size unavailable)` error path → Task 8; region/reset cleanup → Task 10; tests → every task; docs/version → Task 11. No spec requirement is uncovered.
- **Type/name consistency:** `_size_suffix`, `_size_supported`, `_size_on`, `_size_off`, `_cancel_size`, `_cancel_all_sizes`, `_iter_sized_descendants`, `_set_node_size`, `_set_node_size_unavailable`, `_size_worker`, `_size_base_labels`, `_size_workers` are used identically across tasks. `supports_size` / `iter_size` signatures match the ABC.
- **No placeholders:** every code step shows complete code; every run step states the command and expected outcome.
