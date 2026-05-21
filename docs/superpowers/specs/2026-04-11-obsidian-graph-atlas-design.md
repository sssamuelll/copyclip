# Obsidian-Style Force-Directed 3D Graph Codebase Map

**Date:** 2026-04-11
**Scope:** Atlas3DPage — replace planet-scatter with force-directed graph
**Status:** Approved

## Summary

Replace the current Atlas3DPage planet-scatter visualization with an Obsidian-style force-directed 3D graph. Nodes represent modules, edges represent import dependencies. The force simulation organically clusters related modules together. Built on the existing Three.js infrastructure (scene, camera, OrbitControls, starfield, raycaster). The augmented-ui info panel is retained and enhanced with neighbor lists.

## Decisions Made

| Question | Choice | Rationale |
|----------|--------|-----------|
| Graph engine | Force-directed 3D (Three.js + d3-force-3d) | Reuses existing Three.js setup, keeps cosmic aesthetic |
| Edge style | Straight lines, opacity-based | Obsidian-faithful, clean, simple to render |
| Node sizing | By connection count | Communicates structural importance |
| Node color | By cognitive debt level | Core project memory signal — at-a-glance health |
| Labels | Always visible, distance-opacity fade | Obsidian-faithful, billboarded sprites |
| Info panel | Detailed with neighbor list | Shows imports/dependents with debt-colored names |

## Architecture

### Data Flow

```
/api/architecture/graph → { nodes: ArchNode[], edges: ArchEdge[] }
/api/cognitive-load     → { items: CognitiveLoadItem[] }
                              ↓
                    d3-force-3d simulation
                    (computes x, y, z per node)
                              ↓
                    Three.js renders:
                      - Spheres at force positions
                      - LineSegments for edges
                      - Sprites for labels
                              ↓
                    Raycaster handles hover/click
                              ↓
                    Augmented-ui info panel updates
```

### New Dependency

`d3-force-3d` — force simulation in 3D. Runs the physics math (repulsion, spring forces, centering) and outputs x/y/z coordinates. No DOM interaction — coordinates are fed directly into Three.js object positions.

### TypeScript Types

```typescript
// Already exists
type ArchNode = { name: string }

// Needs to be added/confirmed
type ArchEdge = { from: string, to: string, type: string }
```

## Implementation Details

### 1. Force Simulation Setup

```
forceSimulation(nodes)
  .force('charge', forceManyBody().strength(-200))    // repulsion
  .force('link', forceLink(edges).distance(120))      // spring edges
  .force('center', forceCenter(0, 0, 0))              // keep centered
  .force('collide', forceCollide().radius(nodeSize))   // prevent overlap
```

The simulation runs for ~300 ticks on init to settle, then updates positions in the animation loop for any remaining drift.

### 2. Node Rendering

- **Geometry:** `THREE.SphereGeometry` (same as current)
- **Size:** Base radius 6, scaled by `Math.sqrt(connectionCount) * 3`. Minimum 6, maximum 30.
- **Color:** Debt-based via `THREE.MeshStandardMaterial`:
  - debt > 70 → `#ff3333` (red)
  - debt > 40 → `#ffaa00` (amber)
  - else → `#00eeff` (cyan)
- **Emissive:** Same color as base, emissiveIntensity 0.3 at rest, 0.8 on hover/select
- **userData:** Stores `{ name, debt, connectionCount, inbound: string[], outbound: string[] }`

### 3. Edge Rendering

- **Geometry:** `THREE.BufferGeometry` with position attribute for all edge endpoints
- **Material:** `THREE.LineBasicMaterial({ color: 0x00eeff, transparent: true, opacity: 0.15, blending: THREE.AdditiveBlending })`
- **Rendering:** Single `THREE.LineSegments` draw call for all edges (performant)
- **Interaction:** On node hover/select, update edge opacity:
  - Connected edges → opacity 0.5
  - Unconnected edges → opacity 0.05
  - Reset on deselect

### 4. Label Rendering

- **Method:** `THREE.Sprite` with `THREE.CanvasTexture` (same approach as current)
- **Text:** Last path segment of module name (e.g. `server` from `intelligence/server`)
- **Billboarding:** Sprites auto-face camera (built-in Three.js behavior)
- **Distance fade:** In animation loop, compute distance from camera to each label. Opacity = `clamp(1.0 - (distance / maxFadeDistance), 0.1, 0.9)`
- **Position:** Offset below node center by `nodeRadius + 15`

### 5. Info Panel Content (on node select)

```
┌─────────────────────────────────┐ (augmented-ui border)
│ PERSISTENT LINK ESTABLISHED     │
│                                 │
│ intelligence/server             │
│                                 │
│ ┌─────────────────────────────┐ │
│ │ COGNITIVE_DEBT              │ │
│ │ 72.3%                       │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ CONNECTIONS                 │ │
│ │ 12 inbound  ·  8 outbound  │ │
│ └─────────────────────────────┘ │
│                                 │
│ IMPORTS (outbound)              │
│ db · analyzer · agents · cli    │
│                                 │
│ DEPENDENTS (inbound)            │
│ mcp_server · __main__ · scanner │
│                                 │
│ Click deep space to release     │
└─────────────────────────────────┘
```

Neighbor names are color-coded by their own debt level (cyan/amber/red).

### 6. Hover Behavior

- Hovered node: emissive intensity increases, scale lerps to 1.5x
- Connected edges: opacity increases to 0.5
- Connected neighbor nodes: subtle emissive increase (0.5)
- Unconnected edges: fade to 0.05
- Info panel shows in reading state ("Reading project body...")

### 7. Click/Select Behavior

- Selected node: emissive intensity 0.8, scale lerps to 2x
- Info panel switches to locked state ("Persistent link established")
- Edge highlighting persists until deselected
- Click deep space to deselect

## What Gets Removed

- Spiral positioning math (`angle = 22 * t`, `radius = 900 * sqrt(t)`)
- `renderPlanets()` function (replaced by force-positioned nodes)
- Node sizing by cognitive debt (replaced by connection count)
- The `nodesGroup` slow rotation (`nodesGroup.rotation.y += 0.0002`) — force graph should stay static after settling

## What Gets Kept

- Scene setup, background color, fog
- Camera position and perspective settings
- OrbitControls with damping
- Starfield (starsGroup with slow rotation)
- Raycaster mouse interaction pattern
- `highlightPlanet()` / `resetPlanet()` pattern (adapted for new data)
- Augmented-ui info panel container and CSS classes
- Window resize handler
- Loading state overlay

## Files Modified

| File | Change |
|------|--------|
| `frontend/package.json` | Add `d3-force-3d` dependency |
| `frontend/src/types/api.ts` | Add/confirm `ArchEdge` type |
| `frontend/src/pages/Atlas3DPage.tsx` | Rewrite: force simulation, edge rendering, node sizing by connections, label opacity fade, info panel neighbor lists |

## Files NOT Modified

- `frontend/src/styles.css` — augmented-ui panel styles already done
- `frontend/index.html` — augmented-ui CDN already added
- `src/copyclip/intelligence/server.py` — `/api/architecture/graph` already returns nodes + edges
- All other pages and components
