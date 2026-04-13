# Multi-Scale Cosmic Atlas with Progressive Disclosure

**Date:** 2026-04-13
**Scope:** Backend tree endpoint + module resolution fix + Atlas3DPage complete rewrite
**Status:** Approved

## Summary

Replace the flat module-level Atlas with a 4-level zoomable cosmic universe. Each click explodes a node into its internals with cinematic animations. Distinct abstract geometric shapes per level (diamonds, spheres, triangles, squares). HUD labels for at-a-glance awareness. Augmented-ui detail panel on click for inspection. Scroll wheel navigation for spaceship feel. Breadcrumb bar for orientation.

This solves the core problem: projects with flat structure collapsing into a single "root" node with an unreadable info dump.

## Decisions Made

| Question | Choice | Rationale |
|----------|--------|-----------|
| Scale metaphor | Mix A+C: 4-level hierarchy with explode-on-click | Deep cosmic metaphor with progressive disclosure |
| Transitions | Alternating: expand (1→2, 3→4), fly-through (2→3) | Variety prevents animation fatigue |
| Navigation | Scroll wheel + breadcrumb + click deep space | Spaceship feel, orientation, direct jumps |
| Info display | HUD labels in 3D + detail panel on click | Awareness at a glance, deep inspect on dock |
| Visual objects | Abstract geometric (diamond, sphere, triangle, square) | Clean, fast, instantly distinguishable |
| Backend | Hybrid tree: backend folder tree + frontend file→symbol nesting | Clean separation, reuses existing endpoints |

## 4 Zoom Levels

### Level 1: Universe (Project Root)

- **View:** All top-level folders visible as diamond-shaped galaxies floating in the starfield
- **Geometry:** Diamonds (THREE.OctahedronGeometry) with pulsing emissive border
- **Size:** Proportional to total file count inside the folder
- **Color:** Average cognitive debt of contained files (cyan/amber/red)
- **Edges:** Lines connecting folders that have import dependencies between their files
- **HUD labels:** Folder name + file count + avg debt%
- **Interaction:** Click or scroll-in to explode into Level 2

### Level 2: Galaxy (Folder Contents)

- **View:** Files inside the selected folder as glowing spheres, sub-folders as smaller diamonds
- **Geometry:** Spheres (THREE.SphereGeometry) for files, diamonds for sub-folders
- **Size:** Proportional to line count (files) or file count (sub-folders)
- **Color:** Cognitive debt per file (cyan/amber/red)
- **Edges:** Import lines between files within the folder
- **HUD labels:** Filename + line count + debt%
- **Transition IN:** Smooth expand-in-place — parent diamond grows and splits open (~0.8s)
- **Transition OUT:** Reverse collapse animation, or scroll-out
- **Interaction:** Click a file sphere or scroll-in to explode into Level 3. Click a sub-folder diamond to expand it (stays at Level 2).

### Level 3: Star System (File Internals)

- **View:** Classes as triangles (pyramids) and standalone functions as squares (cubes) orbiting the central file sphere
- **Geometry:** Triangles (THREE.ConeGeometry) for classes, squares (THREE.BoxGeometry) for functions
- **Size:** Classes sized by method count, functions sized by complexity
- **Color:** Cognitive debt per symbol
- **Edges:** CALLS edges between functions/classes. INHERITS edges for class hierarchies.
- **HUD labels:** Symbol name + kind + line range
- **Transition IN:** Cinematic fly-through — camera accelerates toward the file sphere, passes through, decelerates into the interior (~1.5s). Surrounding files fade out.
- **Transition OUT:** Reverse fly-out, or scroll-out
- **Interaction:** Click a class triangle or scroll-in to see methods (Level 4). Click a function to open code viewer.

### Level 4: Planet Detail (Class Methods)

- **View:** Methods as small squares orbiting the class triangle. The detail panel shows CodeMirror with the method source.
- **Geometry:** Small cubes (THREE.BoxGeometry) for methods
- **Size:** Proportional to line count
- **Color:** Complexity-based
- **Edges:** CALLS edges between methods
- **HUD labels:** Method name + line range
- **Transition IN:** Smooth expand-in-place — class triangle opens to reveal orbiting method cubes (~0.8s)
- **Transition OUT:** Collapse, or scroll-out
- **Interaction:** Click a method to open CodeMirror at that line in the detail panel.

## Navigation

### Scroll Wheel (Primary — spaceship feel)

- **Scroll in** while hovering a node: zoom into that node (explode to next level)
- **Scroll out** from any level: zoom out to parent level (collapse animation)
- **Scroll in on empty space:** no action (need a target to zoom into)
- **Scroll out at Level 1:** no action (already at universe level)

### Breadcrumb Bar

- Position: top of the Atlas container, below the "// cosmic_project_atlas" header
- Format: `project > src > copyclip > intelligence > server.py`
- Each segment is clickable — jumps directly to that level with a transition animation
- Current level is highlighted in cyan
- Style: small, semi-transparent, doesn't block the view

### Click Deep Space

- **Single click** on empty space: go up one level (collapse animation)
- **At Level 1:** deselect any selected node (existing behavior)

## HUD Labels

- Float in 3D space near each object (THREE.Sprite with CanvasTexture)
- Always face the camera (billboarding)
- Content varies by level:
  - Level 1: `folder_name` + `12 files` + `42%`
  - Level 2: `filename.py` + `2172 ln` + `72%`
  - Level 3: `ClassName` + `class` + `12 methods`
  - Level 4: `method_name` + `ln 120-180`
- Debt percentage colored by threshold (cyan < 40, amber 40-70, red > 70)
- Distance-based opacity fade (existing behavior)

## Detail Panel (Augmented-UI)

The existing augmented-ui panel adapts its content based on the current zoom level. No scroll dumps — only contextually relevant info.

### Level 1 (hover/click a galaxy/folder):
```
PERSISTENT LINK ESTABLISHED
src/copyclip/intelligence
─────────────────────────
FILES          12
SUB-FOLDERS    3
AVG DEBT       42%
HOTTEST        server.py (72%)
─────────────────────────
Click or scroll to enter
```

### Level 2 (hover/click a file):
```
PERSISTENT LINK ESTABLISHED
server.py
─────────────────────────
LINES          2,172
IMPORTS        45
DEBT           72%
─────────────────────────
CLASSES (5)
  IntelligenceHandler
  AnalysisJob
FUNCTIONS (23)
  run_server
  _get_project_id
  ...top 5 by complexity
─────────────────────────
Click or scroll to enter
```

### Level 3 (hover/click a class/function):
```
PERSISTENT LINK ESTABLISHED
IntelligenceHandler
─────────────────────────
CLASS · lines 85-2100
METHODS        12
CALLS          db.connect, analyze
CALLED BY      run_server
INHERITS       BaseHTTPRequestHandler
─────────────────────────
[CodeMirror: class source]
```

### Level 4 (click a method):
```
PERSISTENT LINK ESTABLISHED
do_GET
─────────────────────────
METHOD · lines 120-1850
COMPLEXITY     47
CALLS          _json, with_meta
─────────────────────────
[CodeMirror: method source]
```

## Backend Changes

### New endpoint: `/api/architecture/tree`

Returns the folder hierarchy of the project as a nested tree with aggregated metrics.

```
GET /api/architecture/tree
```

Response:
```json
{
  "name": "root",
  "type": "folder",
  "path": "",
  "children": [
    {
      "name": "src",
      "type": "folder",
      "path": "src",
      "children": [
        {
          "name": "copyclip",
          "type": "folder",
          "path": "src/copyclip",
          "children": [
            {
              "name": "intelligence",
              "type": "folder",
              "path": "src/copyclip/intelligence",
              "children": [
                { "name": "server.py", "type": "file", "path": "src/copyclip/intelligence/server.py", "lines": 2172, "debt": 72, "symbol_count": 45, "language": "python" },
                { "name": "analyzer.py", "type": "file", "path": "src/copyclip/intelligence/analyzer.py", "lines": 1182, "debt": 38, "symbol_count": 30, "language": "python" }
              ],
              "file_count": 8,
              "avg_debt": 42
            }
          ],
          "file_count": 27,
          "avg_debt": 35
        }
      ],
      "file_count": 27,
      "avg_debt": 35
    }
  ],
  "file_count": 120,
  "avg_debt": 30,
  "meta": { "project": "copyclip", "generated_at": "..." }
}
```

Built by querying `files` table for all paths, grouping by directory segments, and aggregating `cognitive_debt` from `analysis_file_insights`. Symbol counts from `symbols` table.

### Fix `_module_from_relpath`

Replace the current 3-line heuristic:
```python
def _module_from_relpath(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) == 1:
        return "root"
    if parts[0] in {"src", "app", "lib"} and len(parts) > 1:
        return parts[1]
    return parts[0]
```

With folder-path-based resolution:
```python
def _module_from_relpath(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) <= 1:
        return "root"
    # Module = parent directory path (without the filename)
    return "/".join(parts[:-1])
```

This means `src/copyclip/intelligence/server.py` becomes module `src/copyclip/intelligence` instead of `copyclip`. Every unique directory path becomes a distinct module in the graph.

### Existing endpoints (unchanged, reused)

- `/api/module/symbols` — provides file→function detail for Level 3/4
- `/api/module/source` — provides source code for CodeMirror in the detail panel
- `/api/architecture/graph` — still used for module-level edge data (now with more granular modules)

## Frontend: Atlas3DPage Rewrite

### State Management

```typescript
type ZoomLevel = 1 | 2 | 3 | 4
type TreeNode = {
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

// State
const [zoomLevel, setZoomLevel] = useState<ZoomLevel>(1)
const [currentPath, setCurrentPath] = useState<string[]>([])  // breadcrumb
const [tree, setTree] = useState<TreeNode | null>(null)
const [selectedNode, setSelectedNode] = useState<any>(null)
```

### Rendering by Level

Each zoom level has a dedicated render function that creates the appropriate Three.js objects:

- `renderUniverse(tree)` — Level 1: diamonds for top-level folders
- `renderGalaxy(folder)` — Level 2: spheres for files, small diamonds for sub-folders
- `renderStarSystem(file, symbols)` — Level 3: triangles for classes, squares for functions
- `renderPlanetDetail(class, symbols)` — Level 4: small squares for methods

### Animation System

Transitions use `TWEEN.js` or manual lerp in the animation loop:

- **Expand-in-place:** Selected node scales up while spawning children that fly outward from center. Other nodes fade and drift away. Duration: ~800ms with ease-out.
- **Fly-through:** Camera position lerps toward the target node. At 60% of the journey, surrounding scene fades. At 80%, new scene fades in. Camera decelerates to final position. Duration: ~1500ms with ease-in-out.
- **Collapse (reverse):** Children fly back to center and merge. Camera pulls back. Parent node reappears. Duration: ~600ms.

### Scroll Wheel Handler

```typescript
renderer.domElement.addEventListener('wheel', (e) => {
  e.preventDefault()
  if (e.deltaY < 0 && hoveredNode) {
    // Scroll in — zoom deeper into hovered node
    zoomInto(hoveredNode)
  } else if (e.deltaY > 0 && zoomLevel > 1) {
    // Scroll out — go up one level
    zoomOut()
  }
}, { passive: false })
```

Note: This replaces the default OrbitControls zoom. OrbitControls still handles rotation and pan.

## Files Modified/Created

| File | Change |
|------|--------|
| `src/copyclip/intelligence/server.py` | Add `/api/architecture/tree` endpoint |
| `src/copyclip/intelligence/analyzer.py` | Fix `_module_from_relpath` for folder-path resolution |
| `frontend/src/pages/Atlas3DPage.tsx` | Complete rewrite: multi-scale, transitions, HUD, breadcrumb |
| `frontend/src/styles.css` | Breadcrumb bar styles |
| `frontend/src/api/client.ts` | Add `architectureTree()` method |
| `frontend/src/types/api.ts` | Add `TreeNode`, `ZoomLevel` types |

## What Stays

- Starfield background and slow rotation
- Augmented-ui panel geometry and CSS
- CodeMirror integration and cosmic theme
- Cognitive debt color scale (cyan/amber/red)
- OrbitControls for rotation and pan (scroll repurposed for zoom levels)
- Lighting setup

## What Gets Removed

- Current flat force-directed graph (replaced by level-specific rendering)
- Single-node-type rendering (replaced by per-level geometries)
- Flat info panel with scroll dump (replaced by contextual per-level panel)
