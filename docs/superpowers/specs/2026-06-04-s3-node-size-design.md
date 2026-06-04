# S3 node size calculation — design

**Date:** 2026-06-04
**Status:** Approved

## Problem

It is useful to know the total size of everything in an S3 bucket or
folder (prefix). Calculating that total is expensive — it requires
enumerating every object beneath the node — so it must not happen
automatically for every bucket, folder, and object. Instead the user
opts in per node with a hotkey, sees the running total climb as the
walk progresses, and can toggle it back off.

## Summary of behaviour

- A new `s` hotkey toggles size display **for the highlighted node**.
- Size is shown in the node's tree label, appended in parentheses:
  `my-folder/ (1.2 GB)`.
- For an **object** node, no walk is needed — the object's size is
  already known, so the label updates instantly.
- For a **bucket** or **prefix** node, the total is the **fully
  recursive** sum of every object beneath it. The walk runs
  asynchronously and the label updates **once per page** (~1000
  objects) so the number visibly climbs.
- Toggling `s` again on a sized node hides the size and cancels any
  in-flight walk.
- Expanding a node that is currently sized **cascades**: each child
  revealed by the expansion is sized too, so the behaviour propagates
  as the user drills deeper.

## Generic plugin seam

Sizing is exposed through the plugin ABC so other services can opt in
later (e.g. total size of all images in an ECR repository). Only S3
implements it for now; every other plugin inherits the no-op default.

Two new methods on `AWSServicePlugin`, mirroring `has_content` /
`get_content`:

```python
def supports_size(self, node: TreeNode) -> bool:
    """Fast, no-AWS check: can this node be sized? Default False."""
    return False

def iter_size(self, session, node) -> Iterator[int]:
    """Yield the cumulative byte total as it grows — one yield per
    chunk of work. The final yielded value is the total.
    Only called when supports_size(node) is True."""
    raise NotImplementedError
```

`iter_size` is a generator yielding the **running cumulative total**.
This shape makes stale-cancellation trivial: the consumer simply stops
iterating, and the plugin's `for page in paginator...` loop ends.

### S3 implementation

`supports_size` returns `True` for `bucket`, `prefix`, and `object`
nodes; `False` for everything else (categories, directory / table /
vector buckets, access points, object versions).

`iter_size`:
- **object** → yields once with the object's size. To avoid an AWS
  call, the `Size` from `list_objects_v2`'s `Contents[]` is stashed
  into each object node's `metadata["size"]` when children are built.
  `iter_size` reads it from metadata.
- **bucket / prefix** → paginates `list_objects_v2` with the node's
  prefix and **no `Delimiter`** (so the listing is fully recursive),
  accumulating `Contents[].Size`, and yields the running total once
  per returned page.

### Shared helper

The existing `_human_bytes(n)` formatter in `s3.py` moves to a new
`awstui/util.py` so both the plugin and the app can format byte totals
consistently. `s3.py` imports it from there.

## App-side orchestration

The app owns the hotkey, the per-node state, and the workers.

### Binding

```python
Binding("s", "toggle_size", "Size")
```

Hidden from the footer via `check_action` when
`supports_size(self._current_node)` is `False` — matching how the
`a`/`u`/`r` copy bindings hide themselves.

### State

- `_size_base_labels: dict[int, str]` — `id(textual_node)` → the node's
  label *without* the size suffix. Same `id()`-keyed pattern the
  existing filter code uses.
- `_size_workers: dict[int, Worker]` — `id(textual_node)` → its
  in-flight walk, so a single node's walk can be cancelled
  independently.

A textual node is "sized" iff its `id()` is a key in
`_size_base_labels`.

### Worker

A **non-exclusive** `@work(thread=True, group="size")` worker per node
(non-exclusive because many nodes may be sizing concurrently during a
cascade). It consumes `plugin.iter_size(session, data)` and, after each
yield, uses `call_from_thread` to update that node's label. Between
yields it checks `get_current_worker().is_cancelled` so toggling off or
a region switch stops the walk within one page.

## Label rendering, toggle, cascade

- **In progress:** `name (⋯ 1.2 GB)` while the total is still climbing.
- **Complete:** `name (1.2 GB)` once the generator is exhausted.
- **Toggle on** (`s` on an unsized node that `supports_size`): record
  its base label, start a worker.
- **Toggle off** (`s` on a sized node): cancel its worker, restore the
  base label, drop it from both dicts. **Symmetric cascade:** turning a
  node off also turns off every descendant it cascaded to — cancel
  their workers and strip their suffixes — since the cascade turned
  them on together.
- **Expand cascade:** the app handles `Tree.NodeExpanded`, which
  bubbles up *after* `AWSNavTree.on_tree_node_expanded` has
  synchronously added the children. If the expanded node is currently
  sized, each child that `supports_size` and is not already sized is
  marked sized and given its own worker. (This covers both first-time
  expansion, where children were just loaded, and re-expansion of a
  node whose children already exist.)

## Error handling & lifecycle

- A walk that raises `ClientError` (e.g. `AccessDenied`) sets the
  node's suffix to `(size unavailable)` and stops. Consistent with the
  inline-error philosophy elsewhere — the user keeps browsing.
- `reset_tree` / region change cancels **all** size workers and clears
  both dicts; sizes are meaningless against a new region/session.
- Sizes live on tree-node labels, not the detail pane, so they persist
  correctly as the user navigates the detail pane around. No
  `_selection_seq` coupling is needed.

## Testing

- **Plugin unit tests:** `supports_size` per node type; `iter_size` for
  an object (single yield read from `metadata["size"]`) and for a
  bucket/prefix (mock paginator returning two pages — assert the
  cumulative yields). A test that the object-child build stashes `Size`
  into metadata.
- **App tests** via Textual's `run_test()` pilot: press `s` on a node
  and assert the label gains a size suffix; press `s` again and assert
  the suffix is stripped. Cascade test: expand a sized node and assert
  its children gain suffixes.
- **Helper move:** update the `_human_bytes` import site and any test
  referencing it.

## Out of scope

- Sizing for non-S3 services (the seam is generic; no other plugin
  implements it yet).
- Persisting computed sizes across region switches or app restarts.
- A detail-pane presentation of size (sizes appear only in the tree
  label for buckets/prefixes; objects already show `Size` in their
  Summary tab).
