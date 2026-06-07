# S3 descendant-size caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Size an S3 bucket/prefix with a single recursive walk, caching every descendant prefix's total so expanding into a sized node serves child sizes from cache with zero extra `list_objects_v2` calls.

**Architecture:** `iter_size` gains a third yielded element — a `dict[node-id → (bytes, count)]` breakdown of descendant prefixes derived during the one walk. The app caches that dict keyed by node-id; `_size_on` short-circuits to the cache on a hit (no worker), otherwise spawns the walk as before. The cache is cleared on region switch / tree reset.

**Tech Stack:** Python 3.12, Textual, boto3, pytest. Run everything via `uv run`.

---

## File structure

- `src/awstui/plugin.py` — `iter_size` contract: 2-tuple → 3-tuple yield + docstring.
- `src/awstui/services/s3.py` — S3 `iter_size` derives the descendant-prefix breakdown; new module-level `_descendant_prefixes` helper.
- `src/awstui/app.py` — `_size_cache` field, `_merge_size_cache`, cache-aware `_size_on`, 3-tuple unpack in `_size_worker`, cache cleared in `_cancel_all_sizes`.
- `tests/test_services/test_s3.py` — update 5 `iter_size` tests to 3-tuples; add a breakdown test.
- `tests/test_app.py` — update the e2e `FakeSizePlugin` to yield 3-tuples; add cache tests.
- `CLAUDE.md` — update the "Node size calculation" wording.

Note throughout: the **Textual** tree node (`.label` / `.set_label` / `.children`, `.data` is the awstui `TreeNode`) is distinct from the **awstui** `TreeNode`. The size helpers in `app.py` take the Textual node; `data` / `node.data` is the awstui one. `_FakeNode` in tests stands in for the Textual node.

---

### Task 1: Widen the `iter_size` contract to a 3-tuple

**Files:**
- Modify: `src/awstui/plugin.py:88-98`

This is a type-and-docstring change only; the abstract body still raises `NotImplementedError`. `test_plugin.py::test_iter_size_default_raises_not_implemented` continues to pass unchanged (the base body has no `yield`, so it's a plain function that raises on call).

- [ ] **Step 1: Update the signature and docstring**

Replace the existing `iter_size` definition (lines 88-98) with:

```python
    def iter_size(
        self, session: boto3.Session, node: TreeNode
    ) -> Iterator[tuple[int, int, dict[str, tuple[int, int]]]]:
        """Yield cumulative `(byte_total, item_count, descendants)` for `node`.

        One yield per chunk of work (e.g. per page of a listing); the final
        yielded `byte_total` / `item_count` are the node's total size and the
        number of items comprising it. Consumers stop iterating to cancel.

        `descendants` maps a descendant node's awstui node-id (the same id
        `get_children` produces) to its cumulative `(bytes, count)`. It lets a
        consumer cache descendant totals so they can be shown later without
        re-walking. It is optional — yield an empty dict when there is no
        cheaper-than-re-walking breakdown to offer (leaf nodes always do).
        Only the final yield's breakdown need be complete.

        Only called when `supports_size(node)` returned True.
        """
        raise NotImplementedError
```

- [ ] **Step 2: Verify the plugin test still passes and types check**

Run: `uv run pytest tests/test_plugin.py -v && uv run mypy src`
Expected: PASS (test_plugin all green); mypy reports no errors.

- [ ] **Step 3: Commit**

```bash
git add src/awstui/plugin.py
git commit -m "feat: widen iter_size contract to yield descendant breakdown"
```

---

### Task 2: Derive the descendant-prefix breakdown in S3 `iter_size`

**Files:**
- Modify: `src/awstui/services/s3.py:527-544` (`iter_size`)
- Create: module-level helper `_descendant_prefixes` in `src/awstui/services/s3.py`
- Test: `tests/test_services/test_s3.py:892-999`

The existing walk already lists every key under the node. We aggregate each key's size into every intermediate directory prefix between the walk root and the key, keyed by the same id `get_children` emits (`s3:prefix:{bucket}:{full_prefix}`). Object nodes yield `(size, 1, {})`. The breakdown is bounded by directory count, not object count; objects are deliberately excluded from it (an object node already sizes itself for free from `metadata["size"]`).

- [ ] **Step 1: Update the existing `iter_size` tests to expect 3-tuples**

In `tests/test_services/test_s3.py`, change these expectations:

`test_iter_size_object_yields_metadata_size_once` (line ~908):
```python
    assert totals == [(789, 1, {})]
```

`test_iter_size_object_missing_size_yields_zero` (line ~926):
```python
    assert list(plugin.iter_size(session, node)) == [(0, 1, {})]
```

`test_iter_size_bucket_yields_cumulative_total_per_page` (line ~952) — keys are `a`, `b`, `c/d` under root prefix `""`, so only `c/` is an intermediate prefix and only on page 2:
```python
    # (cumulative bytes, cumulative object count, descendant breakdown) per page.
    assert totals == [
        (300, 2, {}),
        (350, 3, {"s3:prefix:b:c/": (50, 1)}),
    ]
```

`test_iter_size_prefix_walks_recursively_without_delimiter` (line ~976) — single key `logs/2026/a` under root prefix `logs/`, so `logs/2026/` is the one intermediate prefix:
```python
    assert totals == [(10, 1, {"s3:prefix:b:logs/2026/": (10, 1)})]
```
(Update that test's `paginate.return_value` key from `logs/2026/a` — it currently uses `logs/2026/a` already at line ~961; keep it. The `assert_called_once_with(Bucket="b", Prefix="logs/")` assertion stays.)

`test_iter_size_empty_bucket_yields_zero` (line ~999):
```python
    assert list(plugin.iter_size(session, node)) == [(0, 0, {})]
```

- [ ] **Step 2: Add a test for a multi-level descendant breakdown**

Append to `tests/test_services/test_s3.py`:

```python
def test_iter_size_bucket_breakdown_aggregates_nested_prefixes():
    from awstui.models import TreeNode

    session = make_session()
    client = session.client.return_value
    client.get_paginator.return_value.paginate.return_value = [
        {
            "Contents": [
                {"Key": "logs/2026/01/a", "Size": 10},
                {"Key": "logs/2026/01/b", "Size": 20},
                {"Key": "logs/2026/02/c", "Size": 5},
                {"Key": "top", "Size": 100},
            ]
        },
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
    total, count, descendants = list(plugin.iter_size(session, node))[-1]

    assert (total, count) == (135, 4)
    assert descendants == {
        "s3:prefix:b:logs/": (35, 3),
        "s3:prefix:b:logs/2026/": (35, 3),
        "s3:prefix:b:logs/2026/01/": (30, 2),
        "s3:prefix:b:logs/2026/02/": (5, 1),
    }
    # "top" has no "/" below the root, so it contributes no prefix entry.
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_services/test_s3.py -k iter_size -v`
Expected: FAIL — current `iter_size` yields 2-tuples, so the unpacking / equality assertions fail.

- [ ] **Step 4: Add the `_descendant_prefixes` helper**

Add near the other module-level helpers in `src/awstui/services/s3.py` (e.g. just above `_bucket_versioning_enabled`):

```python
def _descendant_prefixes(root_prefix: str, key: str) -> Iterator[str]:
    """Yield each intermediate directory prefix of `key` below `root_prefix`.

    e.g. root_prefix="logs/", key="logs/2026/01/a" yields
    "logs/2026/", "logs/2026/01/". A key with no "/" below the root yields
    nothing. Each yielded value matches the prefix string `get_children`
    uses to build a prefix node's id.
    """
    if not key.startswith(root_prefix):
        return
    remainder = key[len(root_prefix) :]
    idx = remainder.find("/")
    while idx != -1:
        yield root_prefix + remainder[: idx + 1]
        idx = remainder.find("/", idx + 1)
```

Confirm `Iterator` is already imported in `s3.py` (it is used by the `iter_size` annotation). If not, add `from collections.abc import Iterator`.

- [ ] **Step 5: Update `iter_size` to build the breakdown**

Replace the body of `iter_size` (lines 527-544) with:

```python
    def iter_size(
        self, session: boto3.Session, node: TreeNode
    ) -> Iterator[tuple[int, int, dict[str, tuple[int, int]]]]:
        if node.node_type == "object":
            yield int(node.metadata.get("size") or 0), 1, {}
            return
        # bucket / prefix recursive walk
        client = session.client("s3")
        bucket = node.metadata["bucket_name"]
        prefix = node.metadata.get("prefix", "")
        paginator = client.get_paginator("list_objects_v2")
        total = 0
        count = 0
        descendants: dict[str, tuple[int, int]] = {}
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                size = obj.get("Size", 0)
                total += size
                count += 1
                for p in _descendant_prefixes(prefix, obj["Key"]):
                    node_id = f"s3:prefix:{bucket}:{p}"
                    b, c = descendants.get(node_id, (0, 0))
                    descendants[node_id] = (b + size, c + 1)
            yield total, count, dict(descendants)
```

Both the read (`descendants.get(node_id, ...)`) and write key on the full
`s3:prefix:...` id, so aggregation accumulates correctly across pages.

- [ ] **Step 6: Run the S3 size tests to verify they pass**

Run: `uv run pytest tests/test_services/test_s3.py -k iter_size -v`
Expected: PASS (all `iter_size` tests, including the new breakdown test).

- [ ] **Step 7: Commit**

```bash
git add src/awstui/services/s3.py tests/test_services/test_s3.py
git commit -m "feat: S3 iter_size derives descendant prefix breakdown"
```

---

### Task 3: App cache field, `_merge_size_cache`, and 3-tuple unpack in the worker

**Files:**
- Modify: `src/awstui/app.py:135-138` (init of size state)
- Modify: `src/awstui/app.py:569-588` (`_size_worker`)
- Add: `_merge_size_cache` method in `src/awstui/app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing test for `_merge_size_cache`**

Add to `tests/test_app.py`:

```python
def test_merge_size_cache_updates_from_breakdown():
    app = AWSBrowserApp()
    assert app._size_cache == {}

    app._merge_size_cache({"s3:prefix:b:logs/": (100, 3)})
    assert app._size_cache == {"s3:prefix:b:logs/": (100, 3)}

    # A later walk merges/overwrites without dropping unrelated entries.
    app._merge_size_cache({"s3:prefix:b:logs/2026/": (40, 1)})
    assert app._size_cache == {
        "s3:prefix:b:logs/": (100, 3),
        "s3:prefix:b:logs/2026/": (40, 1),
    }
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_app.py::test_merge_size_cache_updates_from_breakdown -v`
Expected: FAIL — `AWSBrowserApp` has no `_size_cache` attribute.

- [ ] **Step 3: Add the cache field**

In `__init__`, alongside the existing size state (the lines defining `self._size_base_labels` and `self._size_workers`, ~135-138), add:

```python
        # awstui node-id -> cached cumulative (byte_total, item_count) for
        # descendants discovered during a parent's size walk. Lets _size_on
        # serve a child's size without re-walking. Cleared on region switch.
        self._size_cache: dict[str, tuple[int, int]] = {}
```

- [ ] **Step 4: Add `_merge_size_cache`**

Add near the other size helpers (e.g. just after `_set_node_size_unavailable`, ~line 567):

```python
    def _merge_size_cache(self, descendants: dict[str, tuple[int, int]]) -> None:
        """Merge a completed walk's descendant totals into the size cache.

        Called on the UI thread from `_size_worker` after the walk finishes,
        so entries are always authoritative totals, never partials.
        """
        self._size_cache.update(descendants)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_app.py::test_merge_size_cache_updates_from_breakdown -v`
Expected: PASS

- [ ] **Step 6: Update `_size_worker` to unpack the 3-tuple and populate the cache**

Replace the body of `_size_worker` (lines 569-588) with:

```python
    @work(thread=True, group="size")
    def _size_worker(self, node, data: TreeNode) -> None:
        plugin = (
            self._plugin_registry.get(data.service) if self._plugin_registry else None
        )
        if plugin is None or self._session is None:
            return
        worker = get_current_worker()
        total = 0
        count = 0
        descendants: dict[str, tuple[int, int]] = {}
        try:
            for total, count, descendants in plugin.iter_size(self._session, data):
                if worker.is_cancelled:
                    return
                self.call_from_thread(self._set_node_size, node, total, False, count)
            self.call_from_thread(self._set_node_size, node, total, True, count)
            self.call_from_thread(self._merge_size_cache, descendants)
        except ClientError:
            self.call_from_thread(self._set_node_size_unavailable, node)
        except Exception:
            self.call_from_thread(self._set_node_size_unavailable, node)
```

(The `_merge_size_cache` call sits inside the `try` after the success path, so an error mid-walk leaves the cache untouched and children fall back to their own workers.)

- [ ] **Step 7: Verify types and the full app suite still pass**

Run: `uv run mypy src && uv run pytest tests/test_app.py -v`
Expected: mypy clean. test_app FAILS only in the e2e `test_pressing_s_shows_size_in_label_end_to_end` (its `FakeSizePlugin.iter_size` still yields 2-tuples — fixed in Task 5). All other app tests PASS. If any *other* test fails, stop and investigate.

- [ ] **Step 8: Commit**

```bash
git add src/awstui/app.py tests/test_app.py
git commit -m "feat: cache descendant sizes from completed size walk"
```

---

### Task 4: Make `_size_on` cache-aware

**Files:**
- Modify: `src/awstui/app.py:511-516` (`_size_on`)
- Test: `tests/test_app.py`

On a cache hit, `_size_on` records the base label and applies the cached total immediately as a **completed** total (`done=True`), spawning no worker. On a miss it behaves exactly as today.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_app.py`:

```python
def test_size_on_serves_cache_hit_without_worker():
    app = AWSBrowserApp()
    data = _node("prefix", bucket_name="b", prefix="logs/")
    data.id = "s3:prefix:b:logs/"
    node = _FakeNode("logs/", data=data)
    app._size_cache["s3:prefix:b:logs/"] = (2048, 5)

    app._size_on(node)

    # Completed total applied straight from cache; no worker spawned.
    assert node.label == "logs/ (2.0 KB, 5 objects)"
    assert app._size_base_labels[id(node)] == "logs/"
    assert id(node) not in app._size_workers


def test_size_on_cache_miss_spawns_worker(monkeypatch):
    app = AWSBrowserApp()
    data = _node("prefix", bucket_name="b", prefix="logs/")
    data.id = "s3:prefix:b:logs/"
    node = _FakeNode("logs/", data=data)

    spawned = []
    monkeypatch.setattr(
        app, "_size_worker", lambda n, d: spawned.append(n) or _FakeWorker()
    )

    app._size_on(node)

    assert spawned == [node]
    assert app._size_base_labels[id(node)] == "logs/"
    assert node.label == "logs/ (⋯)"
```

(`_node` sets `id="x"`; both tests reassign `data.id` so the cache key matches.)

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_app.py -k "size_on_serves_cache_hit or size_on_cache_miss" -v`
Expected: FAIL — current `_size_on` ignores the cache and always spawns a worker, so the cache-hit test sees `logs/ (⋯)` and a worker entry.

- [ ] **Step 3: Make `_size_on` cache-aware**

Replace `_size_on` (lines 511-516) with:

```python
    def _size_on(self, node) -> None:
        """Start sizing `node`.

        On a size-cache hit (a parent walk already computed this node's total)
        apply the completed total immediately with no worker; otherwise record
        the base label and spawn a walk.
        """
        base = str(node.label)
        data = getattr(node, "data", None)
        cached = self._size_cache.get(data.id) if data is not None else None
        if cached is not None:
            self._size_base_labels[id(node)] = base
            total, count = cached
            self._set_node_size(node, total, done=True, count=count)
            return
        self._size_base_labels[id(node)] = base
        node.set_label(base + " (⋯)")
        self._size_workers[id(node)] = self._size_worker(node, node.data)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_app.py -k "size_on_serves_cache_hit or size_on_cache_miss" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/awstui/app.py tests/test_app.py
git commit -m "feat: _size_on serves cached descendant totals without re-walking"
```

---

### Task 5: Clear the cache on reset; fix the e2e plugin stub

**Files:**
- Modify: `src/awstui/app.py:524-533` (`_cancel_all_sizes`)
- Test: `tests/test_app.py:439-453` (`test_cancel_all_sizes_clears_workers_and_labels`)
- Test: `tests/test_app.py:508-510` (e2e `FakeSizePlugin.iter_size`)

- [ ] **Step 1: Extend the cancel-all test and fix the e2e stub**

In `tests/test_app.py`, update `test_cancel_all_sizes_clears_workers_and_labels` to also assert the cache is cleared. After the existing setup (before `app._cancel_all_sizes()`), seed the cache, and after, assert it is empty:

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
    app._size_cache["s3:prefix:b:logs/"] = (10, 1)

    app._cancel_all_sizes()

    assert w1.cancelled and w2.cancelled
    assert app._size_base_labels == {}
    assert app._size_workers == {}
    assert app._size_cache == {}
```

In the e2e test `test_pressing_s_shows_size_in_label_end_to_end`, update `FakeSizePlugin.iter_size` (lines 508-510) to yield 3-tuples:

```python
        def iter_size(self, session, node):
            yield 500, 1, {}
            yield 1024, 2, {}
```

- [ ] **Step 2: Run both tests to verify the cancel-all one fails**

Run: `uv run pytest tests/test_app.py -k "cancel_all_sizes or pressing_s_shows_size" -v`
Expected: `test_cancel_all_sizes_clears_workers_and_labels` FAILS (cache not cleared yet); the e2e test now PASSES (stub fixed; worker unpacking already handles 3-tuples from Task 3).

- [ ] **Step 3: Clear the cache in `_cancel_all_sizes`**

In `_cancel_all_sizes` (lines 524-533), add a cache clear alongside the existing clears:

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
        self._size_cache.clear()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_app.py -k "cancel_all_sizes or pressing_s_shows_size" -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add src/awstui/app.py tests/test_app.py
git commit -m "feat: clear size cache on region switch; fix e2e size stub"
```

---

### Task 6: Update CLAUDE.md and run the full gate

**Files:**
- Modify: `CLAUDE.md` ("Node size calculation" section)

- [ ] **Step 1: Update the size-calculation docs**

In `CLAUDE.md`, in the "Node size calculation" section, the sentence describing `iter_size` currently reads:

> `iter_size` is a generator yielding cumulative `(byte_total, item_count)` pairs, one yield per chunk of work (S3 yields once per `list_objects_v2` page).

Replace it with:

> `iter_size` is a generator yielding cumulative `(byte_total, item_count, descendants)` triples, one yield per chunk of work (S3 yields once per `list_objects_v2` page). `descendants` maps a descendant node-id → its cumulative `(bytes, count)`; the app caches the final yield's breakdown in `_size_cache` (keyed by awstui node-id) so expanding into an already-sized bucket/prefix serves child sizes from cache with no extra AWS call. `_size_on` short-circuits to the cache on a hit (applying a completed total, no worker); only a cache miss spawns a walk. The one accepted redundancy: expanding a node while its parent's walk is still in flight falls back to a worker, since the child isn't cached yet. `_cancel_all_sizes` clears `_size_cache` along with the worker/label state.

- [ ] **Step 2: Run the full quality gate**

Run:
```bash
uv run ruff format . && uv run ruff check . --fix && uv run mypy src && uv run pytest tests/ -v
```
Expected: ruff makes no/auto-only changes, mypy clean, all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md src tests
git commit -m "docs: document descendant size caching in CLAUDE.md"
```

---

## Self-review notes

- **Spec coverage:** plugin seam (Task 1), S3 breakdown derivation (Task 2), app cache + `_merge_size_cache` + worker unpack (Task 3), cache-aware `_size_on` with `done=True` rendering (Task 4), `_cancel_all_sizes` clears cache + e2e stub fix (Task 5), docs (Task 6). All spec sections mapped.
- **Edge cases from spec:** expand-during-walk fallback is preserved (cache miss → worker, Task 4 miss test); toggle-off of a cache-applied node works because `_cancel_size` already tolerates a missing worker (no new test needed — existing `test_cancel_size_restores_label_and_clears_state` covers the worker-present path, and a cache-applied node simply has no `_size_workers` entry, which `_cancel_size.pop(..., None)` handles); error mid-walk leaves cache untouched (Task 3 `_merge_size_cache` sits after the success path inside `try`).
- **Type consistency:** breakdown type is `dict[str, tuple[int, int]]` everywhere (plugin annotation, S3 `descendants`, `_size_cache`, `_merge_size_cache` arg). The id format `s3:prefix:{bucket}:{p}` matches `get_children`'s prefix-node id exactly.
- **No placeholders:** every code step shows full code; every run step shows the command and expected result.
