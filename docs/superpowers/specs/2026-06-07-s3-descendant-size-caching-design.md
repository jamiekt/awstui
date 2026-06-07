# S3 descendant-size caching

**Date:** 2026-06-07
**Status:** Implemented, with one revision (see "Revision" below)

## Revision (post-smoke-test)

The original design surfaced cached descendant totals **lazily on expand** and
accepted one redundancy: expanding a node *while its parent's walk was still in
flight* fell back to a separate per-child walk, since the child wasn't cached
yet. A smoke test on a very large bucket showed the consequence — N+1
concurrent `list_objects_v2` walks, with the parent's running total visibly
lagging the sum of its children mid-flight (each walk at a different point of
its own progress).

This was reworked: the single root walk now drives **live** updates to every
currently-sized descendant from its per-page breakdown (`_apply_size_progress`),
and cascaded container nodes under an in-flight ancestor spawn **no** worker
(`_size_on` case 2 / `_has_sizing_ancestor`). There is now exactly one walk per
sizing operation; `root_total == direct objects + Σ child-prefix totals` holds
at every page, so the lag is gone. The cache is still committed only on the
final page (so post-completion expansions read authoritative totals). Objects
remain the exception — they size instantly from metadata and keep their own
trivial worker. See "Node size calculation" in `CLAUDE.md` for the current
behaviour; the sections below describe the original lazy design for context.

## Problem

The `s` hotkey toggles recursive size calculation for a tree node (see
"Node size calculation" in `CLAUDE.md`). When a user sizes an S3 bucket or
prefix, `_size_worker` calls `plugin.iter_size(node)`, which for a
bucket/prefix runs a full recursive `list_objects_v2` walk (no delimiter)
summing every object beneath that node.

When the user then expands a sized node, `on_tree_node_expanded` cascades
sizing to each sizeable child by calling `_size_on(child)` — and each child
prefix kicks off **another** full recursive walk over a subset of the keys
the parent walk already enumerated. Drilling down N levels re-walks the same
keys N times.

This is wasteful: a single recursive walk of the bucket already visits every
key and size needed to derive the total of every descendant prefix. The total
of a node equals the sum of its objects plus the sum of its sub-prefixes — all
of which the one walk sees.

Object leaf nodes are **not** part of the waste: they already size themselves
for free from `metadata["size"]` stashed during the children walk, with no
AWS call. The redundancy is entirely in repeated **prefix** walks.

## Goal

One recursive walk per top-level sized node. Descendant prefix totals are
derived from that single walk, cached, and applied when the user expands into
them — with zero additional `list_objects_v2` calls.

The mechanism must stay service-agnostic: the generic plugin contract must not
learn what an S3 "prefix" is. Only the S3 plugin knows how to derive descendant
breakdowns.

## Architecture

One recursive walk populates a process-wide, node-id-keyed cache of descendant
prefix totals. Expanding a sized node serves its children's sizes from that
cache instead of spawning a fresh walk per child. The app caches
`node-id → (bytes, count)` pairs the plugin hands back; it never learns what a
prefix is.

## Components

### 1. Plugin seam (`plugin.py`)

`iter_size` changes its yield from a 2-tuple to a 3-tuple:

```python
def iter_size(
    self, session: boto3.Session, node: TreeNode
) -> Iterator[tuple[int, int, dict[str, tuple[int, int]]]]:
    """Yield cumulative (byte_total, item_count, descendants) for `node`.

    `descendants` maps a descendant node's awstui node-id (the same id
    `get_children` produces) to its cumulative (bytes, count). It is
    optional — yield an empty dict when a plugin has no cheaper-than-
    re-walking breakdown to offer (leaf nodes always do). Consumers may
    cache the breakdown from the final yield to serve descendant sizes
    without re-walking.
    """
```

Leaf nodes yield `{}`. The default implementation still raises
`NotImplementedError`.

### 2. S3 `iter_size` (`s3.py`)

The existing recursive `list_objects_v2` walk already enumerates every key
under the node. Add per-prefix aggregation: for each key, derive the
intermediate directory prefixes **below the walk root**, and add the key's
size (and `+1` to its count) to each. Each intermediate prefix maps to id
`s3:prefix:{bucket}:{p}` — exactly the id `get_children` emits for that prefix.

- Object nodes yield `(size, 1, {})` — no breakdown.
- The breakdown is bounded by **directory count, not object count**.
- Objects are deliberately excluded from the breakdown: an object node already
  sizes itself for free from `metadata["size"]`, so caching it would only
  bloat the dict.
- Only the final yield's breakdown is authoritative; intermediate yields may
  carry a partial dict or `{}` (implementation choice — the app only reads the
  final one).

### 3. App cache (`app.py`)

New `self._size_cache: dict[str, tuple[int, int]]`.

- Populated only from a worker's **final** yield, via a new
  `_merge_size_cache(descendants)` called on the UI thread — so cache entries
  are always authoritative totals, never partials.
- Cleared in `_cancel_all_sizes` (region switch / tree reset) alongside the
  existing `_size_workers` / `_size_base_labels` state.
- Retained across toggle-off (it stays valid until region change), so
  re-sizing a node is instant.

## Data flow

- `_size_worker` unpacks the 3-tuple. It updates its own node's label live as
  before (using `byte_total`/`item_count`), and on successful completion calls
  `_merge_size_cache(descendants)` on the UI thread.
- `_size_on(node)` becomes cache-aware: if `node.data.id` is in `_size_cache`,
  it records the base label and applies the cached total **immediately, with no
  worker** — rendered as a completed total (`done=True`, the `(1.2 GB, N
  objects)` form, not the climbing `(⋯ ...)` form), since a cache entry is
  always an authoritative total. Otherwise it spawns the worker as today.
- `on_tree_node_expanded`'s cascade is unchanged in shape — it still calls
  `_size_on` per sizeable child — but because `_size_on` short-circuits to the
  cache, drilling into a sized bucket fires **zero** new `list_objects_v2`
  walks for prefixes.

## Edge cases

- **Expand while the parent walk is still in flight:** the child isn't cached
  yet, so `_size_on` falls back to a worker — one redundant walk, self-
  completing and correct. Once the parent walk finishes, every later expansion
  is cache-served. This is the single accepted redundancy; it only bites if you
  drill into a bucket mid-walk.
- **Sizing a deep prefix directly after a bucket walk:** served instantly from
  the cache — a free side benefit.
- **Toggle off:** unchanged. `_cancel_size` already tolerates a missing worker,
  which is exactly the state of a cache-applied node (no worker was spawned).
- **Empty prefixes** never appear as `CommonPrefixes`, so a completed walk
  caches every prefix that can ever be a child — "walk done but child uncached"
  cannot happen for prefixes.

## Error handling

Unchanged. A `ClientError` during the walk still routes to
`_set_node_size_unavailable`. On error the cache simply isn't populated (no
`_merge_size_cache` call), so children fall back to their own workers — correct
degradation.

## Testing

- `test_s3.py`: update the 5 existing `iter_size` tests to expect 3-tuples
  (`{}` for object nodes). Add a test asserting the prefix breakdown maps
  `s3:prefix:{bucket}:{p}` ids to correct cumulative `(bytes, count)`.
- `test_app.py`: update `DummyPlugin`/stubs to yield 3-tuples. Add tests that:
  (a) `_size_on` applies a cache hit without spawning a worker;
  (b) `_merge_size_cache` populates from the final yield;
  (c) `_cancel_all_sizes` clears the cache.
- `test_plugin.py`: the default-`NotImplementedError` test is unaffected.

## Out of scope

- Other plugins (only S3 implements `iter_size`).
- All-versions accounting (sizing still counts current object versions only,
  per the existing `list_objects_v2` behaviour).
- Eager subtree construction — descendant sizes surface lazily on expand, not
  by inserting un-opened nodes into the tree.
