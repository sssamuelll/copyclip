# Atlas: Interactive Focus Sets & Graph-Aware Scaling

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port CodeGraphContext's interactive focus set dimming and logarithmic graph-aware node scaling to the CopyClip Atlas, closing issues #5 and #8.

**Architecture:** Two independent improvements to Atlas3DPage.tsx — (1) dim unconnected nodes to 0.05 opacity when a node is hovered/selected, (2) replace the linear `sqrt(connections) * 3` sizing with logarithmic graph-aware scaling that adapts to total graph size.

**Tech Stack:** Three.js (existing), no new dependencies.

---

### File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/src/pages/Atlas3DPage.tsx` | Modify | Both features — focus dimming + scaling |
| `frontend/src/styles.css` | No change | — |
| `frontend/index.html` | No change | — |

---

### Task 1: Add node dimming to highlightEdgesForNode()

**Files:**
- Modify: `frontend/src/pages/Atlas3DPage.tsx` — `highlightEdgesForNode()` function (~line 200)

- [ ] **Step 1: Add node dimming logic**

In `highlightEdgesForNode()`, after the edge split logic, add code to dim all unconnected nodes. The function already highlights connected neighbor nodes at 0.5 emissive. Now we also need to dim unconnected nodes by setting their material opacity low and their emissive to near-zero.

Find this block at the end of `highlightEdgesForNode()`:

```typescript
      // Subtle highlight on connected neighbor nodes
      const node = graphNodes.find(n => n.name === nodeName)
      if (node) {
        const neighbors = new Set([...node.inbound, ...node.outbound])
        nodesGroup.children.forEach(container => {
          const mesh = container.children.find(c => c.type === 'Mesh') as THREE.Mesh | undefined
          if (mesh && mesh !== currentHoveredMesh && mesh !== currentSelectedMesh) {
            const nd = mesh.userData as GraphNode
            if (neighbors.has(nd.name)) {
              ;(mesh.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.5
            }
          }
        })
      }
```

Replace it with:

```typescript
      // Dim unconnected nodes, highlight connected neighbors
      const node = graphNodes.find(n => n.name === nodeName)
      if (node) {
        const neighbors = new Set([...node.inbound, ...node.outbound])
        nodesGroup.children.forEach(container => {
          const mesh = container.children.find(c => c.type === 'Mesh') as THREE.Mesh | undefined
          if (!mesh || mesh === currentHoveredMesh || mesh === currentSelectedMesh) return
          const nd = mesh.userData as GraphNode
          const mat = mesh.material as THREE.MeshStandardMaterial
          const label = container.children.find(c => c.type === 'Sprite') as THREE.Sprite | undefined
          if (neighbors.has(nd.name)) {
            mat.emissiveIntensity = 0.5
            mat.opacity = 1.0
            if (label) (label.material as THREE.SpriteMaterial).opacity = 0.8
          } else {
            mat.transparent = true
            mat.opacity = 0.08
            mat.emissiveIntensity = 0.05
            if (label) (label.material as THREE.SpriteMaterial).opacity = 0.05
          }
        })
      }
```

- [ ] **Step 2: Ensure node materials support transparency**

In `renderNodes()`, the `THREE.MeshStandardMaterial` must have `transparent: true` set at creation time so opacity changes work. Find:

```typescript
        const material = new THREE.MeshStandardMaterial({
          color,
          roughness: 0.4,
          metalness: 0.3,
          emissive: color,
          emissiveIntensity: 0.3,
        })
```

Replace with:

```typescript
        const material = new THREE.MeshStandardMaterial({
          color,
          roughness: 0.4,
          metalness: 0.3,
          emissive: color,
          emissiveIntensity: 0.3,
          transparent: true,
          opacity: 1.0,
        })
```

- [ ] **Step 3: Update resetEdges() to restore node opacity**

In `resetEdges()`, find the node reset block:

```typescript
      // Reset neighbor highlights
      nodesGroup.children.forEach(container => {
        const mesh = container.children.find(c => c.type === 'Mesh') as THREE.Mesh | undefined
        if (mesh && mesh !== currentHoveredMesh && mesh !== currentSelectedMesh) {
          ;(mesh.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.3
        }
      })
```

Replace with:

```typescript
      // Reset all node visuals to default
      nodesGroup.children.forEach(container => {
        const mesh = container.children.find(c => c.type === 'Mesh') as THREE.Mesh | undefined
        if (mesh && mesh !== currentHoveredMesh && mesh !== currentSelectedMesh) {
          const mat = mesh.material as THREE.MeshStandardMaterial
          mat.emissiveIntensity = 0.3
          mat.opacity = 1.0
          const label = container.children.find(c => c.type === 'Sprite') as THREE.Sprite | undefined
          if (label) (label.material as THREE.SpriteMaterial).opacity = 0.7
        }
      })
```

- [ ] **Step 4: Build and verify**

Run:
```bash
cd frontend && npm run build
```
Expected: Clean build, no errors.

- [ ] **Step 5: Sync bundle and manual test**

```bash
cp frontend/dist/index.html src/copyclip/intelligence/ui/index.html
```

Manual test: run `copyclip start`, open Atlas, hover a node. Unconnected nodes should fade to near-invisible. Connected neighbors stay bright. Release hover — all nodes restore.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Atlas3DPage.tsx
git commit -m "feat(atlas): dim unconnected nodes on focus (#5)"
```

---

### Task 2: Graph-aware logarithmic node scaling

**Files:**
- Modify: `frontend/src/pages/Atlas3DPage.tsx` — `getNodeRadius()` function and `buildGraph()` where it's called

- [ ] **Step 1: Add clamp helper and replace getNodeRadius()**

Find the current `getNodeRadius`:

```typescript
    const getNodeRadius = (connectionCount: number) => {
      return Math.max(6, Math.min(30, 6 + Math.sqrt(connectionCount) * 3))
    }
```

Replace with:

```typescript
    const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

    const getNodeRadius = (connectionCount: number, totalNodes: number) => {
      // Graph-aware scale: adapts node sizes to total graph density
      // Ported from CodeGraphContext's getGraphAwareNodeScale()
      const graphScale = clamp(1 + Math.log10(Math.max(totalNodes, 1)) * 0.22, 1, 2)
      const degreeSize = Math.log2(connectionCount + 1) * 4
      return clamp((4 + degreeSize) * graphScale, 5, 35)
    }
```

- [ ] **Step 2: Update all getNodeRadius() call sites**

There are 3 call sites. Update each to pass `graphNodes.length`:

**In `buildGraph()` — force collide radius:**

Find:
```typescript
        .force('collide', forceCollide().radius((d: GraphNode) => getNodeRadius(d.connectionCount) + 5))
```

Replace with:
```typescript
        .force('collide', forceCollide().radius((d: GraphNode) => getNodeRadius(d.connectionCount, graphNodes.length) + 5))
```

**In `renderNodes()` — sphere geometry and label offset:**

Find:
```typescript
        const radius = getNodeRadius(node.connectionCount)
```

Replace with:
```typescript
        const radius = getNodeRadius(node.connectionCount, nodes.length)
```

- [ ] **Step 3: Build and verify**

Run:
```bash
cd frontend && npm run build
```
Expected: Clean build, no errors.

- [ ] **Step 4: Sync bundle and manual test**

```bash
cp frontend/dist/index.html src/copyclip/intelligence/ui/index.html
```

Manual test: run `copyclip start`, open Atlas. Nodes should be proportionally sized — high-connection nodes visibly larger than low-connection ones, but the scale should feel balanced regardless of total graph size.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Atlas3DPage.tsx
git commit -m "feat(atlas): graph-aware logarithmic node scaling (#8)"
```

---

### Task 3: Final sync and verify

- [ ] **Step 1: Final build and sync**

```bash
cd frontend && npm run build && cp dist/index.html ../src/copyclip/intelligence/ui/index.html
```

- [ ] **Step 2: Full manual test**

Run `copyclip start`, open Atlas. Verify:
1. Nodes are logarithmically scaled by connection count
2. Hovering a node dims all unconnected nodes + their labels to near-invisible
3. Connected neighbors stay bright with slight emissive boost
4. Edges still brighten for connected, dim for unconnected
5. Clicking a node locks the focus (persistent link established)
6. Clicking deep space releases — all nodes restore to full opacity
7. Info panel still shows connections, imports, dependents correctly

- [ ] **Step 3: Commit bundle**

```bash
git add src/copyclip/intelligence/ui/index.html
git commit -m "build(ui): sync atlas bundle with focus sets and scaling"
```
