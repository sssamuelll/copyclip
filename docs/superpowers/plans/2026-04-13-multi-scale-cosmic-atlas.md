# Multi-Scale Cosmic Atlas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat single-node Atlas with a 4-level zoomable cosmic universe where each click explodes a node into its internals, with distinct shapes per level, HUD labels, scroll-wheel navigation, and a breadcrumb bar.

**Architecture:** Backend provides a nested folder tree via `/api/architecture/tree`. Frontend Atlas3DPage is rewritten with a level-based rendering system — each zoom level has its own render function, geometry types, and transition animations. OrbitControls handles rotation/pan, scroll wheel handles zoom-level changes.

**Tech Stack:** Three.js (existing), Python (backend endpoint), TypeScript/React (frontend)

---

### File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/copyclip/intelligence/analyzer.py` | Modify | Fix `_module_from_relpath` for folder-path resolution |
| `src/copyclip/intelligence/server.py` | Modify | Add `/api/architecture/tree` endpoint |
| `frontend/src/types/api.ts` | Modify | Add `TreeNode` type |
| `frontend/src/api/client.ts` | Modify | Add `architectureTree()` method |
| `frontend/src/pages/Atlas3DPage.tsx` | Rewrite | Multi-scale rendering, transitions, navigation |
| `frontend/src/styles.css` | Modify | Breadcrumb bar styles |

---

### Task 1: Fix `_module_from_relpath` for folder-path resolution

**Files:**
- Modify: `src/copyclip/intelligence/analyzer.py`

- [ ] **Step 1: Replace the module resolution function**

Find in `src/copyclip/intelligence/analyzer.py`:

```python
def _module_from_relpath(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) == 1:
        return "root"
    if parts[0] in {"src", "app", "lib"} and len(parts) > 1:
        return parts[1]
    return parts[0]
```

Replace with:

```python
def _module_from_relpath(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) <= 1:
        return "root"
    return "/".join(parts[:-1])
```

- [ ] **Step 2: Run existing tests**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
python3 -m pytest tests/test_intelligence_analyzer.py -v
```

Expected: All pass (the function isn't directly tested, but ensure no regressions).

- [ ] **Step 3: Commit**

```bash
git add src/copyclip/intelligence/analyzer.py
git commit -m "fix(analyzer): use folder-path module resolution instead of top-level heuristic"
```

---

### Task 2: Add `/api/architecture/tree` endpoint

**Files:**
- Modify: `src/copyclip/intelligence/server.py`

- [ ] **Step 1: Add the tree endpoint**

Find in `src/copyclip/intelligence/server.py` the architecture graph block:

```python
            if parsed.path == "/api/architecture/graph":
```

Insert the new endpoint BEFORE it:

```python
            if parsed.path == "/api/architecture/tree":
                if not pid:
                    self._json(with_meta({"name": "root", "type": "folder", "path": "", "children": [], "file_count": 0, "avg_debt": 0}))
                    return

                # Get all files with their metrics
                rows = conn.execute(
                    """SELECT f.path, f.language, f.size_bytes,
                              COALESCE(a.cognitive_debt, 0) as debt,
                              (SELECT COUNT(*) FROM symbols s WHERE s.project_id=? AND s.file_path=f.path) as symbol_count
                       FROM files f
                       LEFT JOIN analysis_file_insights a ON a.project_id=f.project_id AND a.path=f.path
                       WHERE f.project_id=?
                       ORDER BY f.path""",
                    (pid, pid),
                ).fetchall()

                # Build nested tree from flat file paths
                tree = {"name": "root", "type": "folder", "path": "", "children": [], "file_count": 0, "avg_debt": 0}

                for fpath, lang, size_bytes, debt, sym_count in rows:
                    parts = fpath.split("/")
                    current = tree
                    # Navigate/create folder nodes
                    for i, part in enumerate(parts[:-1]):
                        folder_path = "/".join(parts[:i+1])
                        existing = None
                        for child in current["children"]:
                            if child["name"] == part and child["type"] == "folder":
                                existing = child
                                break
                        if not existing:
                            existing = {"name": part, "type": "folder", "path": folder_path, "children": [], "file_count": 0, "avg_debt": 0}
                            current["children"].append(existing)
                        current = existing
                    # Add file node
                    lines = 0
                    if size_bytes:
                        try:
                            fp = Path(root) / fpath
                            if fp.exists():
                                lines = sum(1 for _ in open(fp, "rb"))
                        except Exception:
                            lines = max(1, size_bytes // 40)
                    current["children"].append({
                        "name": parts[-1], "type": "file", "path": fpath,
                        "lines": lines, "debt": round(debt, 1),
                        "symbol_count": sym_count or 0, "language": lang or "",
                    })

                # Aggregate folder metrics (file_count, avg_debt) bottom-up
                def _aggregate(node):
                    if node["type"] == "file":
                        return 1, node.get("debt", 0)
                    total_files = 0
                    total_debt = 0.0
                    for child in node.get("children", []):
                        fc, td = _aggregate(child)
                        total_files += fc
                        total_debt += td
                    node["file_count"] = total_files
                    node["avg_debt"] = round(total_debt / max(total_files, 1), 1)
                    return total_files, total_debt

                _aggregate(tree)

                # Collapse single-child folders (e.g. src/copyclip → src/copyclip)
                def _collapse(node):
                    if node["type"] == "file":
                        return node
                    node["children"] = [_collapse(c) for c in node["children"]]
                    if len(node["children"]) == 1 and node["children"][0]["type"] == "folder" and node["name"] != "root":
                        child = node["children"][0]
                        child["name"] = node["name"] + "/" + child["name"]
                        return child
                    return node

                tree = _collapse(tree)

                self._json(with_meta(tree))
                return

```

- [ ] **Step 2: Test with curl**

```bash
curl -s "http://localhost:4310/api/architecture/tree" | python3 -m json.tool | head -40
```

Expected: Nested JSON tree with folders and files.

- [ ] **Step 3: Commit**

```bash
git add src/copyclip/intelligence/server.py
git commit -m "feat(api): add /api/architecture/tree endpoint for hierarchical project view"
```

---

### Task 3: Frontend types and API client

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add TreeNode type**

In `frontend/src/types/api.ts`, find the `ArchNode` type and add BEFORE it:

```typescript
export type TreeNode = {
  name: string
  type: 'folder' | 'file'
  path: string
  children?: TreeNode[]
  lines?: number
  debt?: number
  symbol_count?: number
  file_count?: number
  avg_debt?: number
  language?: string
}

export type ArchNode = { name: string }
```

- [ ] **Step 2: Add API method**

In `frontend/src/api/client.ts`, add `TreeNode` to the import from `'../types/api'`, and add after `architecture`:

```typescript
  architectureTree: () => getJSON<TreeNode>('/api/architecture/tree'),
```

- [ ] **Step 3: Build**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/client.ts
git commit -m "feat(api): add architectureTree client method and TreeNode type"
```

---

### Task 4: Breadcrumb bar styles

**Files:**
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add breadcrumb styles**

In `frontend/src/styles.css`, find `/* --- Atlas Code Viewer --- */` and add BEFORE it:

```css
/* --- Atlas Breadcrumb --- */
.atlas-breadcrumb {
  position: absolute;
  top: 70px;
  left: 30px;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-family: 'IBM Plex Mono', monospace;
  z-index: 10;
  pointer-events: auto;
}

.atlas-breadcrumb-segment {
  color: #555;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 3px;
  transition: color 0.15s ease, background 0.15s ease;
}

.atlas-breadcrumb-segment:hover {
  color: #00eeff;
  background: rgba(0, 238, 255, 0.05);
}

.atlas-breadcrumb-segment--active {
  color: #00eeff;
}

.atlas-breadcrumb-separator {
  color: #333;
  font-size: 9px;
  user-select: none;
}

```

- [ ] **Step 2: Build**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles.css
git commit -m "style: add Atlas breadcrumb navigation styles"
```

---

### Task 5: Atlas3DPage rewrite — core infrastructure

This is the biggest task. The Atlas3DPage.tsx is rewritten with the multi-scale rendering system. Due to the size, this task establishes the core infrastructure: state management, tree loading, level rendering dispatch, and Level 1 (Universe) rendering.

**Files:**
- Rewrite: `frontend/src/pages/Atlas3DPage.tsx`

- [ ] **Step 1: Write the complete new Atlas3DPage.tsx**

Read the plan file for the full implementation:
```bash
cat /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/docs/superpowers/specs/2026-04-13-multi-scale-cosmic-atlas-design.md
```

The new file must implement:

**Core state:**
```typescript
type ZoomLevel = 1 | 2 | 3 | 4
// State:
// - tree: TreeNode (from /api/architecture/tree)
// - zoomLevel: ZoomLevel (1-4)
// - currentPath: string[] (breadcrumb segments)
// - currentNode: TreeNode (the node we're "inside")
// - selectedNode: any (for the detail panel)
// - hoveredNode: any (for HUD highlight)
```

**Level rendering functions:**
- `renderLevel1(tree)` — Diamonds (OctahedronGeometry) for top-level folders. Force-positioned. Sized by file_count. Colored by avg_debt.
- `renderLevel2(folder)` — Spheres for files, small diamonds for sub-folders. Sized by lines/file_count. Colored by debt.
- `renderLevel3(file, symbols)` — Cones for classes, boxes for functions. Fetches symbols from `/api/module/symbols`. Sized by method count/complexity. Colored by debt.
- `renderLevel4(classNode, symbols)` — Small boxes for methods. Fetches from symbols data.

**Each render function must:**
1. Clear the nodesGroup
2. Create the appropriate Three.js geometries
3. Position them (force-directed or orbital layout)
4. Add HUD labels (Sprite with CanvasTexture)
5. Store metadata in `userData` for raycasting

**Transitions:**
- `zoomInto(node)` — Depending on level:
  - 1→2, 3→4: expand-in-place (scale up selected, fade out others, spawn children)
  - 2→3: fly-through (lerp camera toward node, fade scene, render new scene)
- `zoomOut()` — Reverse the transition, go up one level

**Navigation:**
- Scroll wheel: `wheel` event on renderer.domElement — scroll in = `zoomInto(hoveredNode)`, scroll out = `zoomOut()`
- Breadcrumb: click a segment to jump to that level
- Click deep space: go up one level

**HUD labels:**
- Same Sprite + CanvasTexture approach as before
- Content varies by level (see spec)
- Debt% colored by threshold

**Detail panel:**
- Reuse existing augmented-ui panel
- Content adapts to current zoom level (see spec for each level's content)
- CodeMirror appears at Level 3/4

**Important implementation notes:**
- Disable OrbitControls zoom (`.enableZoom = false`) — scroll wheel is repurposed for level navigation
- Keep OrbitControls rotation and pan
- Keep the starfield background
- Keep the existing augmented-ui panel geometry and CSS
- The force simulation (d3-force-3d) is used at every level for node positioning
- At Level 3, fetch symbols via `api.moduleSymbols(modulePath)` where modulePath = the file's parent folder path
- At Level 4, use the symbols already fetched at Level 3

**The file should be approximately 500-700 lines.** Key sections:
1. Imports and types (~30 lines)
2. Helper functions: createHUDLabel, getDebtColor, nodeGeometryForLevel (~60 lines)
3. Component state and refs (~20 lines)
4. Main useEffect: scene setup, lighting, starfield, controls, event handlers (~80 lines)
5. renderLevel1, renderLevel2, renderLevel3, renderLevel4 (~200 lines total)
6. zoomInto, zoomOut transition functions (~100 lines)
7. Scroll wheel + mouse handlers (~50 lines)
8. Animation loop (~30 lines)
9. JSX: breadcrumb, detail panel (adapts to level), loading state (~100 lines)

- [ ] **Step 2: Build**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build
```

Expected: Clean build.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Atlas3DPage.tsx
git commit -m "feat(atlas): multi-scale cosmic universe with 4 zoom levels, transitions, and HUD"
```

---

### Task 6: Build, sync, and verify

- [ ] **Step 1: Final build and sync**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build && cp dist/index.html ../src/copyclip/intelligence/ui/index.html
```

- [ ] **Step 2: Re-analyze project to populate new module paths**

The module resolution changed, so existing analysis data uses old module names. Re-analyze:

```bash
copyclip analyze
```

This repopulates modules with folder-path-based names and rebuilds the dependency graph.

- [ ] **Step 3: Full manual test**

Run `copyclip start`, open Atlas. Verify:

1. **Level 1 (Universe):** Multiple diamonds visible (one per top-level folder: src, tests, frontend, docs, etc.). Not a single "root" blob.
2. **Scroll in** on a diamond: it expands to show files as spheres (Level 2).
3. **Breadcrumb** appears showing the path. Click a segment to jump back.
4. **Scroll in** on a file sphere: cinematic fly-through to Level 3 showing classes (cones) and functions (boxes).
5. **HUD labels** visible near each object with name and debt%.
6. **Detail panel** shows contextual info per level (no scroll dump).
7. **Click deep space** or scroll out: goes back up one level.
8. **Starfield** still visible at all levels.
9. **OrbitControls** rotation and pan still work. Scroll only changes levels.

- [ ] **Step 4: Commit bundle**

```bash
git add src/copyclip/intelligence/ui/index.html
git commit -m "build(ui): sync atlas bundle with multi-scale cosmic universe"
```

- [ ] **Step 5: Push to main**

```bash
git push origin main
```
