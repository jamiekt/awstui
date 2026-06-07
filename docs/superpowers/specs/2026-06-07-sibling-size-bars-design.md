# Sibling-relative size bars behind tree labels

**Date:** 2026-06-07
**Status:** Approved, pending implementation plan

## Problem

The `s` hotkey computes a node's recursive size and shows it in the tree label
(`logs/ (1.2 GB, 3,402 objects)`). Numbers alone make it hard to eyeball which
children dominate a folder. A visual gauge — a data bar behind each label whose
length is proportional to that node's share of its parent — lets the user spot
the big consumers at a glance.

## Overview

After a folder is sized via `s`, each sized node renders a subtle background
"data bar" behind its label. The filled width is proportional to that node's
share of its **parent's total** (`node_bytes / parent_bytes`), so a child taking
69% of its parent fills ~69% of the row's width. Bars appear only on nodes with
computed sizes — no new AWS calls; the feature rides entirely on the existing
size machinery. The bar is a faint, low-contrast background shade: text glyphs
and foreground colours are never altered, so labels stay fully legible.

## Key property: bars do NOT depend on label width

The bar length is measured against the **row width**, not the label text width:

- `bar_cells = round(fraction * available_width)`, where `available_width` is
  the row's content width (pane content width minus this node's indentation
  depth) — a property of the row, not of the text in it.
- **Siblings share the same `available_width`** (same tree depth → same indent,
  same pane), so a 69% bar and a 5% bar are fractions of the *same* cell count
  and are directly comparable regardless of differing label lengths.
- **Padding to full row width is load-bearing.** The label `Text` is padded
  with trailing spaces to the full row width *before* the background style is
  applied, so a short label (`tmp/ (80 MB)`) can still show a long bar (painted
  mostly over blank trailing cells), and a long label can show a short bar.
  Without the pad, the bar could only span as far as actual characters exist,
  which would wrongly couple bar length to text length.

### Accepted visual caveats

- **Long label, short bar:** the label text extends past the shaded region onto
  plain background. Expected and fine.
- **Indent narrows deeper rows:** a bar at depth 5 spans fewer absolute cells
  than one at depth 1. Bars are only meaningful *within* a sibling group (share
  of the same parent), and we never compare bars across different parents, so
  this is correct by construction.

## Components & data flow

### 1. Fraction source — `_size_values` on the app (`app.py`)

The size machinery already computes each sized node's `(bytes, count)`. Add one
dict, `self._size_values: dict[int, int]` (keyed by `id(textual_node)` →
byte total), maintained alongside the existing `_size_base_labels`:

- **Populate:** set `self._size_values[id(node)] = total` in `_set_node_size`,
  the single funnel through which every real total reaches a node (climbing
  `done=False` updates, the final `done=True` update, and `_size_on`'s cache-hit
  path, which also calls `_set_node_size`). Populating here means one edit
  covers all paths, and bars grow during the walk. Set it *after*
  `_set_node_size`'s existing `id(node) not in _size_base_labels` early-return
  guard, so stale/toggled-off nodes never get a stray entry.
- **Clear:** `del`/`pop` in `_cancel_size` (per node) and `.clear()` in
  `_cancel_all_sizes` (region switch / tree reset), exactly alongside
  `_size_base_labels`. "Size unavailable" nodes never get an entry.

The **fraction is computed at render time, not stored**, so it self-corrects as
siblings finish sizing mid-walk.

### 2. Fraction lookup — pure helper (`nav_tree.py` or `app.py`)

A small pure function given a node's own bytes and its parent's bytes returns
`own / parent` as a float in [0, 1], or `None` when no bar should show:

- parent not sized (no entry) → `None` (share-of-parent undefined)
- parent total == 0 → `None` (divide-by-zero guard)
- node not sized → `None`

The nav tree needs read access to `_size_values`. The tree already holds a
reference path to the app (it posts messages to it); the simplest wiring is for
the app to pass/set the `_size_values` dict on the tree, or expose a callback
the tree calls with a Textual node. Implementation plan picks the lighter of the
two; the contract is: **given a Textual node, return `fraction | None`.**

### 3. Rendering — `AWSNavTree.render_label` override (`nav_tree.py`)

Textual 8.2.1 signature: `render_label(self, node, base_style, style) -> Text`.

1. `text = super().render_label(node, base_style, style)` — the normal label
   (icon prefix + name + size suffix), untouched.
2. Look up `fraction` for `node`. If `None`, return `text` unchanged.
3. Compute `available_width` = the tree's content region width minus this node's
   indentation (depth * indent guide width). Compute
   `bar_cells = clamp(round(fraction * available_width), 0, available_width)`.
4. If `bar_cells == 0`, return `text` unchanged.
5. Pad `text` with trailing spaces to `available_width` cells, then
   `text.stylize(Style(bgcolor=<faint shade>), 0, bar_cells)` to shade the first
   `bar_cells` cells' **backgrounds only**.
6. Return `text`.

Because `render_label` runs on every paint, the bar tracks resize / pane-grow /
expand-collapse automatically. The faint shade is a dim background colour close
to the panel background (exact token chosen in the plan, e.g. a muted
`$primary`/`$panel`-derived colour); foreground text is never restyled.

This lives entirely in `nav_tree.py`; `app.py` only maintains `_size_values`.

## Error handling

- Missing/zero/parent-less data → no bar (helper returns `None`); never raises.
- `available_width` non-positive (extremely narrow pane) → `bar_cells` clamps to
  0 → no bar.
- The override always falls back to the plain `super().render_label` result, so
  any unexpected state degrades to today's behaviour.

## Testing

- **Pure helpers (unit):**
  - `_size_bar_cells(fraction, width)`: rounding, clamp to `[0, width]`,
    `0.0 → 0`, `1.0 → width`, negative/over-1 inputs clamp.
  - fraction lookup: `own/parent`; missing parent → `None`; zero parent →
    `None`; missing own → `None`.
- **Render (unit):** construct a tree node with known own/parent `_size_values`,
  call `render_label`, assert the returned `Text` has a background-styled span
  covering exactly the first N cells and no background beyond N; assert a
  `None`-fraction node returns a `Text` with no added background span.
- **State lifecycle:** `_size_values` is populated by `_set_node_size`, cleared
  by `_cancel_size` and `_cancel_all_sizes` (extend or mirror the existing size
  tests).
- Existing label-string tests stay valid — `set_label` content is unchanged;
  the bar is purely a render-time background overlay.

## Out of scope

- Bars on un-sized nodes (would require auto-sizing on expand — rejected; keeps
  the opt-in, no-extra-AWS-calls model).
- All-versions accounting — bars inherit the existing current-object-versions-
  only totals from the size walk; consistent with the numbers in the labels.
- Cross-parent comparison / global-scale bars — bars are sibling-relative only.
- Bars in the detail pane — this is a nav-tree visual only.
