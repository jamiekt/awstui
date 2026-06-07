# Sibling-relative size bars Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render a faint background "data bar" behind each sized tree node's label, proportional to that node's share of its parent's total size.

**Architecture:** The app records each sized node's byte total in a new `_size_values` dict (keyed by `id(textual_node)`), populated wherever sizes are applied and cleared alongside the other size state. `AWSNavTree` overrides Textual's `render_label` to read that dict, compute `fraction = own / parent_total` at render time, and shade the first `fraction * available_width` cells of the label's background — leaving all text glyphs and foreground colours untouched.

**Tech Stack:** Python 3.12, Textual 8.2.1, Rich, pytest. Run everything via `uv run`.

---

## Background facts (verified against Textual 8.2.1)

- Override point: `Tree.render_label(self, node, base_style, style) -> Text`. The returned `Text` is the label region only (icon prefix + label); indentation guides are prepended separately in `_render_line`.
- A node's indentation in cells = `depth(node) * self.guide_depth`, where `depth` is the number of ancestors up to (not including) the root, and `guide_depth` defaults to 4. So the label region's width = `self.size.width - depth(node) * self.guide_depth`.
- `node.parent` is available on a Textual `TreeNode`; the root's `.parent` is `None`.
- `Text.stylize(Style(bgcolor=...), start, end)` applies a **background** over cells `[start, end)` additively — foreground spans/glyphs are preserved. Verified: `Text("logs/").pad_right(...); .stylize(Style(bgcolor="blue"), 0, 8)` yields a single bg span `(0, 8)`.
- `self.size.width` is `0` on an unmounted widget, so width must be injectable for unit tests (we extract `_available_bar_width`).

## File structure

- `src/awstui/app.py` — new `self._size_values: dict[int, int]`; populate in `_set_node_size`, pop in `_cancel_size` and `_set_node_size_unavailable`, clear in `_cancel_all_sizes`; wire the dict onto the tree in `on_mount`.
- `src/awstui/widgets/nav_tree.py` — `size_values` attribute; pure helper `_size_bar_cells`; methods `_node_depth`, `_available_bar_width`, `_size_fraction`, `_paint_size_bar`; `render_label` override; a `_SIZE_BAR_BG` colour constant.
- `tests/test_app.py` — `_size_values` lifecycle tests.
- `tests/test_services/` — n/a.
- `tests/test_nav_tree.py` — helper + render tests (create if absent; otherwise append).
- `CLAUDE.md` — document the bar in the "Node size calculation" section.

Terminology: the **Textual** tree node has `.label`/`.set_label`/`.children`/`.parent`, and `.data` is the awstui `TreeNode`. `_size_values` is keyed by `id(textual_node)`, exactly like `_size_base_labels`.

---

### Task 1: Record sized nodes' byte totals in `_size_values`

**Files:**
- Modify: `src/awstui/app.py` (`__init__` size-state block ~135-142; `_set_node_size` ~588; `_set_node_size_unavailable`; `_cancel_size` ~573; `_cancel_all_sizes` ~561)
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_app.py` (near the other size tests; `_FakeNode` / `_FakeWorker` already exist):

```python
def test_size_values_populated_by_set_node_size():
    app = AWSBrowserApp()
    node = _FakeNode("logs/")
    app._size_base_labels[id(node)] = "logs/"  # tracked

    app._set_node_size(node, 2048, done=False, count=5)
    assert app._size_values[id(node)] == 2048

    app._set_node_size(node, 4096, done=True, count=9)
    assert app._size_values[id(node)] == 4096  # updates on done too


def test_set_node_size_skips_size_values_when_untracked():
    app = AWSBrowserApp()
    node = _FakeNode("logs/")
    # NOT in _size_base_labels -> early return, no entry recorded.
    app._set_node_size(node, 2048, done=True, count=5)
    assert id(node) not in app._size_values


def test_size_unavailable_drops_size_values_entry():
    app = AWSBrowserApp()
    node = _FakeNode("logs/")
    app._size_base_labels[id(node)] = "logs/"
    app._size_values[id(node)] = 999  # stale prior total

    app._set_node_size_unavailable(node)
    assert id(node) not in app._size_values


def test_cancel_size_drops_size_values_entry():
    app = AWSBrowserApp()
    node = _FakeNode("logs/")
    app._size_base_labels[id(node)] = "logs/"
    app._size_values[id(node)] = 2048

    app._cancel_size(node)
    assert id(node) not in app._size_values


def test_cancel_all_sizes_clears_size_values():
    app = AWSBrowserApp()
    n = _FakeNode("a")
    app._size_base_labels[id(n)] = "a"
    app._size_values[id(n)] = 10

    app._cancel_all_sizes()
    assert app._size_values == {}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_app.py -k "size_values or size_unavailable_drops" -v`
Expected: FAIL — `AWSBrowserApp` has no `_size_values` attribute.

- [ ] **Step 3: Add the `_size_values` field**

In `__init__`, after the `self._size_cache: dict[str, tuple[int, int]] = {}` line (~142), add:

```python
        # id(textual TreeNode) -> its computed byte total. Drives the
        # sibling-relative size bar in the nav tree (shared by reference with
        # AWSNavTree.size_values). Lifecycle mirrors _size_base_labels.
        self._size_values: dict[int, int] = {}
```

- [ ] **Step 4: Populate in `_set_node_size` (after the tracked-guard)**

`_set_node_size` currently early-returns when the node is untracked. Record the total *after* that guard so stale/toggled-off nodes never get an entry. Change the start of the method from:

```python
    def _set_node_size(self, node, total: int, done: bool, count: int) -> None:
        base = self._size_base_labels.get(id(node))
        if base is None:
            # Toggled off (or region-switched) while the walk was in flight.
            return
```

to:

```python
    def _set_node_size(self, node, total: int, done: bool, count: int) -> None:
        base = self._size_base_labels.get(id(node))
        if base is None:
            # Toggled off (or region-switched) while the walk was in flight.
            return
        self._size_values[id(node)] = total
```

- [ ] **Step 5: Drop the entry in `_set_node_size_unavailable` and `_cancel_size`**

In `_set_node_size_unavailable`, after its own `base is None` guard, add the pop. The method currently is:

```python
    def _set_node_size_unavailable(self, node) -> None:
        base = self._size_base_labels.get(id(node))
        if base is None:
            return
        node.set_label(base + self._SIZE_UNAVAILABLE_SUFFIX)
```

Change to:

```python
    def _set_node_size_unavailable(self, node) -> None:
        base = self._size_base_labels.get(id(node))
        if base is None:
            return
        self._size_values.pop(id(node), None)
        node.set_label(base + self._SIZE_UNAVAILABLE_SUFFIX)
```

In `_cancel_size`, add the pop alongside the existing pops:

```python
    def _cancel_size(self, node) -> None:
        worker = self._size_workers.pop(id(node), None)
        if worker is not None:
            worker.cancel()
        self._size_values.pop(id(node), None)
        base = self._size_base_labels.pop(id(node), None)
        if base is not None:
            node.set_label(base)
```

- [ ] **Step 6: Clear in `_cancel_all_sizes`**

Add `self._size_values.clear()` alongside the existing clears:

```python
        self._size_workers.clear()
        self._size_base_labels.clear()
        self._size_cache.clear()
        self._size_values.clear()
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_app.py -k "size_values or size_unavailable_drops" -v`
Expected: PASS (all 5).

- [ ] **Step 8: Commit**

```bash
git add src/awstui/app.py tests/test_app.py
git commit -m "$(cat <<'EOF'
feat: record sized nodes' byte totals in _size_values

Lifecycle mirrors _size_base_labels: populated in _set_node_size (after
the tracked guard), dropped in _cancel_size / _set_node_size_unavailable,
cleared in _cancel_all_sizes. Feeds the upcoming nav-tree size bar.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Pure helpers in the nav tree (cells, depth, width, fraction)

**Files:**
- Modify: `src/awstui/widgets/nav_tree.py` (imports; `__init__`; new helpers)
- Test: `tests/test_nav_tree.py` (create if absent)

- [ ] **Step 1: Write the failing tests**

Create or append to `tests/test_nav_tree.py`:

```python
from unittest.mock import MagicMock

from awstui.widgets.nav_tree import AWSNavTree, _size_bar_cells


def _tree():
    return AWSNavTree(MagicMock(), [])


def test_size_bar_cells_rounding_and_clamp():
    assert _size_bar_cells(0.0, 20) == 0
    assert _size_bar_cells(1.0, 20) == 20
    assert _size_bar_cells(0.5, 20) == 10
    assert _size_bar_cells(0.69, 16) == 11  # round(11.04)
    # Clamp out-of-range inputs.
    assert _size_bar_cells(-0.5, 20) == 0
    assert _size_bar_cells(1.5, 20) == 20
    # Non-positive width -> no bar.
    assert _size_bar_cells(0.5, 0) == 0
    assert _size_bar_cells(0.5, -3) == 0


class _FakeTN:
    """Stand-in for a Textual TreeNode (has .parent)."""

    def __init__(self, parent=None):
        self.parent = parent


def test_size_fraction_own_over_parent():
    tree = _tree()
    parent = _FakeTN()
    child = _FakeTN(parent=parent)
    tree.size_values = {id(parent): 1000, id(child): 690}
    assert tree._size_fraction(child) == 0.69


def test_size_fraction_none_when_parent_unsized():
    tree = _tree()
    parent = _FakeTN()
    child = _FakeTN(parent=parent)
    tree.size_values = {id(child): 690}  # parent missing
    assert tree._size_fraction(child) is None


def test_size_fraction_none_when_own_unsized():
    tree = _tree()
    parent = _FakeTN()
    child = _FakeTN(parent=parent)
    tree.size_values = {id(parent): 1000}  # child missing
    assert tree._size_fraction(child) is None


def test_size_fraction_none_when_parent_total_zero():
    tree = _tree()
    parent = _FakeTN()
    child = _FakeTN(parent=parent)
    tree.size_values = {id(parent): 0, id(child): 0}
    assert tree._size_fraction(child) is None


def test_size_fraction_none_when_no_parent():
    tree = _tree()
    root = _FakeTN(parent=None)
    tree.size_values = {id(root): 500}
    assert tree._size_fraction(root) is None


def test_node_depth_counts_ancestors():
    tree = _tree()
    root = _FakeTN()
    a = _FakeTN(parent=root)
    b = _FakeTN(parent=a)
    assert tree._node_depth(root) == 0
    assert tree._node_depth(a) == 1
    assert tree._node_depth(b) == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_nav_tree.py -v`
Expected: FAIL — `_size_bar_cells` / `size_values` / `_size_fraction` / `_node_depth` don't exist yet.

- [ ] **Step 3: Add the `size_values` attribute**

In `AWSNavTree.__init__`, after `self._original_labels: dict[int, str] = {}` (~54), add:

```python
        # id(textual TreeNode) -> byte total, shared by reference from the app
        # (AWSBrowserApp._size_values). Drives the sibling-relative size bar in
        # render_label. Empty until the app wires it up in on_mount.
        self.size_values: dict[int, int] = {}
```

- [ ] **Step 4: Add the module-level `_size_bar_cells` helper**

Near the top of `nav_tree.py`, after the `_FILTER_ICON` constant (~15), add:

```python
def _size_bar_cells(fraction: float, width: int) -> int:
    """Number of cells to shade for a bar of `fraction` over `width` cells.

    Clamps `fraction` to [0, 1] and the result to [0, width]; returns 0 for a
    non-positive width.
    """
    if width <= 0:
        return 0
    fraction = max(0.0, min(1.0, fraction))
    return max(0, min(width, round(fraction * width)))
```

- [ ] **Step 5: Add the `_node_depth`, `_available_bar_width`, and `_size_fraction` methods**

Add these methods to `AWSNavTree` (e.g. after `__init__` / the `session` property, before `on_mount`):

```python
    def _node_depth(self, node) -> int:
        """Number of ancestors between `node` and the root (root -> 0)."""
        depth = 0
        parent = node.parent
        while parent is not None:
            depth += 1
            parent = parent.parent
        return depth

    def _available_bar_width(self, node) -> int:
        """Cells available for the label region of `node`'s row.

        Equals the tree's content width minus this node's indentation
        (`depth * guide_depth`). 0 (no bar) when unmounted or too narrow.
        """
        return max(0, self.size.width - self._node_depth(node) * self.guide_depth)

    def _size_fraction(self, node) -> float | None:
        """`node`'s byte total as a fraction of its parent's, or None.

        None when the node or its parent has no recorded size, the node has no
        parent, or the parent total is 0.
        """
        own = self.size_values.get(id(node))
        parent = node.parent
        if own is None or parent is None:
            return None
        parent_total = self.size_values.get(id(parent))
        if not parent_total:  # None or 0
            return None
        return own / parent_total
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_nav_tree.py -v`
Expected: PASS (all helper tests).

- [ ] **Step 7: Commit**

```bash
git add src/awstui/widgets/nav_tree.py tests/test_nav_tree.py
git commit -m "$(cat <<'EOF'
feat: nav-tree size-bar helpers (cells, depth, width, fraction)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Paint the bar in `render_label` and wire the dict from the app

**Files:**
- Modify: `src/awstui/widgets/nav_tree.py` (`_SIZE_BAR_BG` constant; `_paint_size_bar`; `render_label`)
- Modify: `src/awstui/app.py` (`on_mount`, after `tree = AWSNavTree(...)` ~194)
- Test: `tests/test_nav_tree.py`

- [ ] **Step 1: Write the failing render tests**

Append to `tests/test_nav_tree.py`:

```python
from rich.style import Style


def _bg_span_len(text):
    """Total cells covered by spans that set a background colour."""
    return sum(
        (span.end - span.start)
        for span in text.spans
        if isinstance(span.style, Style) and span.style.bgcolor is not None
    )


def test_render_label_paints_bar_for_sized_node(monkeypatch):
    tree = _tree()
    parent = tree.root.add("bucket")
    child = parent.add("logs/")
    tree.size_values = {id(parent): 1000, id(child): 500}  # 50%
    # Fixed available width so the test is mount-independent.
    monkeypatch.setattr(tree, "_available_bar_width", lambda node: 20)

    text = tree.render_label(child, Style(), Style())

    # 50% of 20 = 10 cells shaded; label padded to >= 20 cells.
    assert _bg_span_len(text) == 10
    assert text.cell_len >= 20


def test_render_label_no_bar_when_unsized(monkeypatch):
    tree = _tree()
    parent = tree.root.add("bucket")
    child = parent.add("logs/")
    # Nothing in size_values -> fraction None.
    monkeypatch.setattr(tree, "_available_bar_width", lambda node: 20)

    text = tree.render_label(child, Style(), Style())
    assert _bg_span_len(text) == 0


def test_render_label_no_bar_when_width_zero(monkeypatch):
    tree = _tree()
    parent = tree.root.add("bucket")
    child = parent.add("logs/")
    tree.size_values = {id(parent): 1000, id(child): 500}
    monkeypatch.setattr(tree, "_available_bar_width", lambda node: 0)

    text = tree.render_label(child, Style(), Style())
    assert _bg_span_len(text) == 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_nav_tree.py -k render_label -v`
Expected: FAIL — `render_label` not yet overridden, so no background span is added.

- [ ] **Step 3: Add the colour constant and `_paint_size_bar`**

Near the other constants in `nav_tree.py` (after `_FILTER_ICON`), add:

```python
# Faint, low-contrast background for the sibling-relative size bar. Chosen to
# sit close to the panel background so label text stays legible; tune freely.
_SIZE_BAR_BG = "#2b3a4a"
```

Add the painting method to `AWSNavTree`:

```python
    def _paint_size_bar(self, text: Text, node) -> Text:
        """Shade the first `fraction * width` cells of `text`'s background.

        No-op (returns `text` unchanged) when the node has no size fraction or
        no room. Pads `text` to the full available width first so a short label
        can still show a long bar. Only the background is styled; foreground
        glyphs and colours are untouched, keeping the label readable.
        """
        fraction = self._size_fraction(node)
        if fraction is None:
            return text
        width = self._available_bar_width(node)
        cells = _size_bar_cells(fraction, width)
        if cells <= 0:
            return text
        if text.cell_len < width:
            text.pad_right(width - text.cell_len)
        text.stylize(Style(bgcolor=_SIZE_BAR_BG), 0, cells)
        return text
```

- [ ] **Step 4: Override `render_label`**

Add to `AWSNavTree`:

```python
    def render_label(self, node, base_style, style):
        text = super().render_label(node, base_style, style)
        return self._paint_size_bar(text, node)
```

(`Style` must be importable — add `from rich.style import Style` to the imports at the top of `nav_tree.py` if not already present. `Text` is already imported.)

- [ ] **Step 5: Run the render tests to verify they pass**

Run: `uv run pytest tests/test_nav_tree.py -k render_label -v`
Expected: PASS (3 render tests).

- [ ] **Step 6: Wire the app's dict onto the tree**

In `app.py` `on_mount`, immediately after `tree = AWSNavTree(self._session, plugins)` (~194) and before `nav_pane.mount(tree)`, add:

```python
        tree.size_values = self._size_values  # share by reference for the size bar
```

(Sharing the same dict object means the app's `_set_node_size` / `_cancel_*` mutations are visible to the tree's `render_label` with no further plumbing. `_cancel_all_sizes` clears it in place, so the reference stays valid across region switches.)

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add src/awstui/widgets/nav_tree.py src/awstui/app.py tests/test_nav_tree.py
git commit -m "$(cat <<'EOF'
feat: render sibling-relative size bar behind nav-tree labels

render_label shades the first fraction*width cells of a sized node's
label background (faint, foreground untouched). The app shares its
_size_values dict with the tree by reference.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Document the bar and run the full gate

**Files:**
- Modify: `CLAUDE.md` ("Node size calculation" section)

- [ ] **Step 1: Add a paragraph to the size docs**

In `CLAUDE.md`, at the end of the "Node size calculation" section (after the current-versions-only paragraph), add:

```markdown
Sized nodes also get a **sibling-relative size bar**: a faint background shade behind the label spanning `node_bytes / parent_bytes` of the row's width, so a child filling most of its parent shows a long bar. The app records each sized node's byte total in `_size_values` (keyed by `id(textual_node)`, lifecycle mirroring `_size_base_labels`) and shares that dict by reference with `AWSNavTree`. `AWSNavTree.render_label` computes the fraction at paint time (own / parent total, from `size_values`) and shades the first `fraction * available_width` cells of the label's *background* only — text glyphs and foreground colours are untouched, so labels stay legible. `available_width` is the row content width minus the node's indentation (`depth * guide_depth`), so bars track resize/pane-grow and are only comparable within a sibling group. No bar shows when the node or its parent is unsized, the parent total is 0, or the pane is too narrow.
```

- [ ] **Step 2: Run the full quality gate**

Run:
```bash
uv run ruff format . && uv run ruff check . && uv run mypy src && uv run pytest tests/ -v
```
Expected: ruff clean (auto-format only), mypy clean, all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document the sibling-relative size bar

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** fraction source / `_size_values` lifecycle (Task 1); pure helpers + fraction lookup with all None cases (Task 2); `render_label` background overlay, padding-to-width, no-bar fallbacks (Task 3); CLAUDE.md docs (Task 4). The spec's "key property: bars don't depend on label width" is realised by `_available_bar_width` (row-based, not text-based) + `pad_right` before shading, asserted by `test_render_label_paints_bar_for_sized_node` (label padded to >= width, 10/20 shaded).
- **Type consistency:** `_size_values: dict[int, int]` on both the app and the tree (shared by reference); `_size_bar_cells(fraction: float, width: int) -> int`; `_size_fraction(node) -> float | None`; `_available_bar_width(node) -> int`; `_node_depth(node) -> int`. `render_label` matches Textual's `(node, base_style, style) -> Text`.
- **No placeholders:** every step shows full code and an exact command with expected result.
- **Out-of-scope honoured:** no auto-sizing on expand, no all-versions accounting, no theme-token plumbing (a tunable constant instead — noted as adjustable).
