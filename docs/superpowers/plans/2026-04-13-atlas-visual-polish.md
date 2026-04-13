# Atlas Visual Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Atlas from flat cyan diamonds into a living cosmic universe with color variety, glow effects, vast scale, visible connections, and intuitive navigation.

**Architecture:** All changes are in `Atlas3DPage.tsx` — modifying helper functions, render functions, interaction handlers, and the animation loop. No backend changes. One CSS addition for a hint overlay.

**Tech Stack:** Three.js (existing), no new dependencies.

---

### File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/src/pages/Atlas3DPage.tsx` | Modify | All 8 visual fixes |
| `frontend/src/styles.css` | Modify | Navigation hint overlay style |

---

### Task 1: Color variety — assign colors by folder identity, not just debt

**Files:**
- Modify: `frontend/src/pages/Atlas3DPage.tsx`

The problem: `getDebtColor()` returns cyan for everything under 40% debt. Since most folders have 0% debt, the entire universe is monotone cyan.

- [ ] **Step 1: Add a folder color palette**

Find at the top of the file (after the `clamp` function around line 40):

```typescript
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
```

Add AFTER it:

```typescript
/** Color palette for cosmic objects — each folder/file gets a distinct hue */
const COSMIC_PALETTE = [
  0x00eeff, // cyan
  0xae63e4, // purple
  0xff6b6b, // coral
  0xffaa00, // amber
  0x47cf73, // green
  0x5e91f2, // blue
  0xff3c96, // pink
  0x2bc7b9, // teal
  0xf0e130, // gold
  0xff8d41, // orange
]

/** Get a consistent color for a node based on its name hash */
const getNodeColor = (name: string, debt: number): number => {
  // High debt always shows red/amber regardless of palette
  if (debt > 70) return 0xff3333
  if (debt > 50) return 0xffaa00
  // Otherwise, assign from palette based on name
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = ((hash << 5) - hash + name.charCodeAt(i)) | 0
  return COSMIC_PALETTE[Math.abs(hash) % COSMIC_PALETTE.length]
}

/** Color for file nodes based on language */
const getLanguageColor = (lang: string, debt: number): number => {
  if (debt > 70) return 0xff3333
  if (debt > 50) return 0xffaa00
  const langColors: Record<string, number> = {
    python: 0x3572A5,
    javascript: 0xf0e130,
    typescript: 0x3178c6,
    css: 0x563d7c,
    cpp: 0xf34b7d,
    rust: 0xdea584,
    json: 0x47cf73,
    markdown: 0x888888,
    html: 0xe34c26,
    other: 0x666666,
  }
  return langColors[lang] || 0x888888
}
```

- [ ] **Step 2: Update renderLevel1 to use palette colors**

Find in `renderLevel1`:

```typescript
        const debt = child.avg_debt || 0
        const geo = new THREE.OctahedronGeometry(sizes[i], 0)
```

Replace `getDebtColor(debt)` with `getNodeColor(child.name, debt)` in the `addNodeMesh` call. Find:

```typescript
        addNodeMesh(geo, getDebtColor(debt), positions[i], lbl, { treeNode: child, level: 1 }, -(sizes[i] + 18))
```

Replace with:

```typescript
        addNodeMesh(geo, getNodeColor(child.name, debt), positions[i], lbl, { treeNode: child, level: 1 }, -(sizes[i] + 18))
```

- [ ] **Step 3: Update renderLevel2 to use language colors for files**

Find in `renderLevel2`:

```typescript
        const debt = child.type === 'file' ? (child.debt || 0) : (child.avg_debt || 0)
```

And the `addNodeMesh` call below it. Change `getDebtColor(debt)` to:

```typescript
        const color = child.type === 'file'
          ? getLanguageColor(child.language || 'other', debt)
          : getNodeColor(child.name, debt)
```

And use `color` instead of `getDebtColor(debt)` in the `addNodeMesh` call.

- [ ] **Step 4: Build and verify**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
git add frontend/src/pages/Atlas3DPage.tsx
git commit -m "feat(atlas): color variety — folder palette + language colors for files"
```

---

### Task 2: Glow halos — add an outer transparent sphere to each node

**Files:**
- Modify: `frontend/src/pages/Atlas3DPage.tsx`

- [ ] **Step 1: Add glow sphere to addNodeMesh**

Find the `addNodeMesh` function:

```typescript
    const addNodeMesh = (
      geometry: THREE.BufferGeometry,
      color: number,
      pos: THREE.Vector3,
      label: THREE.Sprite,
      meta: NodeMeta,
      labelOffset: number,
    ) => {
      const g = new THREE.Group()
      const mat = new THREE.MeshStandardMaterial({
        color, roughness: 0.4, metalness: 0.3,
        emissive: color, emissiveIntensity: 0.3,
        transparent: true, opacity: 1.0,
      })
      const mesh = new THREE.Mesh(geometry, mat)
      mesh.userData = meta
      g.add(mesh)
      label.position.set(0, labelOffset, 0)
      g.add(label)
      g.position.copy(pos)
      nodesGroup.add(g)
    }
```

Replace with:

```typescript
    const addNodeMesh = (
      geometry: THREE.BufferGeometry,
      color: number,
      pos: THREE.Vector3,
      label: THREE.Sprite,
      meta: NodeMeta,
      labelOffset: number,
    ) => {
      const g = new THREE.Group()
      const mat = new THREE.MeshStandardMaterial({
        color, roughness: 0.3, metalness: 0.4,
        emissive: color, emissiveIntensity: 0.4,
        transparent: true, opacity: 1.0,
      })
      const mesh = new THREE.Mesh(geometry, mat)
      mesh.userData = meta
      g.add(mesh)

      // Glow halo — outer transparent sphere
      const glowSize = geometry.boundingSphere?.radius || 10
      geometry.computeBoundingSphere()
      const glowGeo = new THREE.SphereGeometry((geometry.boundingSphere?.radius || 10) * 1.6, 16, 12)
      const glowMat = new THREE.MeshBasicMaterial({
        color, transparent: true, opacity: 0.08,
        side: THREE.BackSide, blending: THREE.AdditiveBlending,
      })
      const glow = new THREE.Mesh(glowGeo, glowMat)
      glow.userData = { _glow: true } // mark as glow, skip raycasting
      g.add(glow)

      label.position.set(0, labelOffset, 0)
      g.add(label)
      g.position.copy(pos)
      nodesGroup.add(g)
    }
```

- [ ] **Step 2: Exclude glow meshes from raycasting**

Find in `getMeshUnderMouse`:

```typescript
      const hit = hits.find(h => (h.object as any).isMesh && (h.object as THREE.Mesh).userData?.level)
```

Replace with:

```typescript
      const hit = hits.find(h => (h.object as any).isMesh && (h.object as THREE.Mesh).userData?.level && !(h.object as THREE.Mesh).userData?._glow)
```

- [ ] **Step 3: Build and commit**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
git add frontend/src/pages/Atlas3DPage.tsx
git commit -m "feat(atlas): add glow halos to cosmic objects"
```

---

### Task 3: Vast universe — increase layout spread and camera distance

**Files:**
- Modify: `frontend/src/pages/Atlas3DPage.tsx`

- [ ] **Step 1: Increase Level 1 spread and camera distance**

Find in `renderLevel1`:

```typescript
      const positions = forceLayout(children.length, i => sizes[i], 80)
```

Replace with:

```typescript
      const positions = forceLayout(children.length, i => sizes[i], 250)
```

Find in `renderLevel1`:

```typescript
      camera.position.set(0, 300, 900)
```

Replace with:

```typescript
      camera.position.set(0, 500, 1500)
```

- [ ] **Step 2: Increase Level 2 spread**

Find in `renderLevel2`:

```typescript
      const positions = forceLayout(children.length, i => sizes[i], 60)
```

Replace with:

```typescript
      const positions = forceLayout(children.length, i => sizes[i], 180)
```

Find in `renderLevel2`:

```typescript
      camera.position.set(0, 200, 600)
```

Replace with:

```typescript
      camera.position.set(0, 350, 1000)
```

- [ ] **Step 3: Increase size contrast**

Find in `renderLevel1`:

```typescript
      const sizes = children.map(c => clamp(Math.sqrt(c.file_count || 1) * 4, 6, 40))
```

Replace with (more dramatic scaling):

```typescript
      const sizes = children.map(c => clamp(Math.log2((c.file_count || 1) + 1) * 8, 8, 50))
```

Find in `renderLevel2`:

```typescript
      const sizes = children.map(c =>
        c.type === 'file'
          ? clamp(Math.sqrt(c.lines || 100) * 0.6, 5, 30)
          : clamp(Math.sqrt(c.file_count || 1) * 3, 5, 25),
      )
```

Replace with:

```typescript
      const sizes = children.map(c =>
        c.type === 'file'
          ? clamp(Math.log2((c.lines || 100) + 1) * 3, 5, 35)
          : clamp(Math.log2((c.file_count || 1) + 1) * 7, 6, 30),
      )
```

- [ ] **Step 4: Build and commit**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
git add frontend/src/pages/Atlas3DPage.tsx
git commit -m "feat(atlas): vast universe — increased spread, camera distance, size contrast"
```

---

### Task 4: Scroll anywhere — zoom into nearest node when scrolling on empty space

**Files:**
- Modify: `frontend/src/pages/Atlas3DPage.tsx`

- [ ] **Step 1: Update onWheel handler**

Find:

```typescript
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      if (T.transitioning) return
      if (event.deltaY < 0 && T.hoveredMesh) {
        // Scroll in: zoom into hovered node
        const meta = T.hoveredMesh.userData as NodeMeta
        zoomInto(meta)
      } else if (event.deltaY > 0 && T.zoomLevel > 1) {
        // Scroll out: go up one level
        zoomOut()
      }
    }
```

Replace with:

```typescript
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      if (T.transitioning) return
      if (event.deltaY < 0) {
        // Scroll in: zoom into hovered node, or nearest node if hovering space
        let targetMesh = T.hoveredMesh
        if (!targetMesh) {
          // Find nearest node to mouse ray
          const rect = renderer.domElement.getBoundingClientRect()
          mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
          mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
          raycaster.setFromCamera(mouse, camera)
          let nearest: THREE.Mesh | null = null
          let nearestDist = Infinity
          nodesGroup.children.forEach(g => {
            const mesh = g.children.find(c => (c as any).isMesh && (c as THREE.Mesh).userData?.level) as THREE.Mesh | undefined
            if (mesh) {
              const dist = raycaster.ray.distanceToPoint(g.position)
              if (dist < nearestDist) {
                nearestDist = dist
                nearest = mesh
              }
            }
          })
          if (nearest && nearestDist < 200) targetMesh = nearest
        }
        if (targetMesh) {
          const meta = targetMesh.userData as NodeMeta
          zoomInto(meta)
        }
      } else if (event.deltaY > 0 && T.zoomLevel > 1) {
        zoomOut()
      }
    }
```

- [ ] **Step 2: Build and commit**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
git add frontend/src/pages/Atlas3DPage.tsx
git commit -m "feat(atlas): scroll anywhere zooms into nearest node"
```

---

### Task 5: Hover/click visual feedback — scale, brighten, dim others

**Files:**
- Modify: `frontend/src/pages/Atlas3DPage.tsx`

- [ ] **Step 1: Enhance hover effect with neighbor dimming**

Find in `onMouseMove`, the hover-on section:

```typescript
          T.hoveredMesh = mesh
          const mat = mesh.material as THREE.MeshStandardMaterial
          mat.emissiveIntensity = 0.8
          setHoveredMeta(mesh.userData as NodeMeta)
```

Replace with:

```typescript
          T.hoveredMesh = mesh
          const mat = mesh.material as THREE.MeshStandardMaterial
          mat.emissiveIntensity = 1.0
          // Dim other nodes
          nodesGroup.children.forEach(g => {
            const m = g.children.find(c => (c as any).isMesh && (c as THREE.Mesh).userData?.level) as THREE.Mesh | undefined
            if (m && m !== mesh) {
              const mmat = m.material as THREE.MeshStandardMaterial
              mmat.opacity = 0.2
              mmat.emissiveIntensity = 0.1
            }
          })
          setHoveredMeta(mesh.userData as NodeMeta)
```

Find the hover-off section (when no mesh is hit):

```typescript
        if (T.hoveredMesh && T.hoveredMesh !== T.selectedMesh) {
          const mat = T.hoveredMesh.material as THREE.MeshStandardMaterial
          mat.emissiveIntensity = 0.3
        }
        T.hoveredMesh = null
        setHoveredMeta(null)
        renderer.domElement.style.cursor = 'default'
```

Replace with:

```typescript
        if (T.hoveredMesh && T.hoveredMesh !== T.selectedMesh) {
          const mat = T.hoveredMesh.material as THREE.MeshStandardMaterial
          mat.emissiveIntensity = 0.4
        }
        T.hoveredMesh = null
        // Restore all nodes
        nodesGroup.children.forEach(g => {
          const m = g.children.find(c => (c as any).isMesh && (c as THREE.Mesh).userData?.level) as THREE.Mesh | undefined
          if (m && m !== T.selectedMesh) {
            const mmat = m.material as THREE.MeshStandardMaterial
            mmat.opacity = 1.0
            mmat.emissiveIntensity = 0.4
          }
        })
        setHoveredMeta(null)
        renderer.domElement.style.cursor = 'default'
```

- [ ] **Step 2: Also reset previous hover in the hover-on reset block**

Find:

```typescript
          if (T.hoveredMesh && T.hoveredMesh !== T.selectedMesh) {
            const mat = T.hoveredMesh.material as THREE.MeshStandardMaterial
            mat.emissiveIntensity = 0.3
          }
```

Replace with:

```typescript
          if (T.hoveredMesh && T.hoveredMesh !== T.selectedMesh) {
            const mat = T.hoveredMesh.material as THREE.MeshStandardMaterial
            mat.emissiveIntensity = 0.4
          }
```

- [ ] **Step 3: Build and commit**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
git add frontend/src/pages/Atlas3DPage.tsx
git commit -m "feat(atlas): hover dims other nodes, brightens target"
```

---

### Task 6: Bigger labels + navigation hint

**Files:**
- Modify: `frontend/src/pages/Atlas3DPage.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Increase label size**

Find in `createHUDLabel`:

```typescript
  sprite.scale.set(140, 140 * (canvas.height / canvas.width), 1)
```

Replace with:

```typescript
  sprite.scale.set(200, 200 * (canvas.height / canvas.width), 1)
```

Also increase font size. Find:

```typescript
  ctx.font = '300 28px IBM Plex Mono'
```

Replace with:

```typescript
  ctx.font = '300 34px IBM Plex Mono'
```

- [ ] **Step 2: Add navigation hint CSS**

In `frontend/src/styles.css`, find `/* --- Atlas Breadcrumb --- */` and add BEFORE it:

```css
/* --- Atlas Navigation Hint --- */
.atlas-nav-hint {
  position: absolute;
  bottom: 30px;
  left: 30px;
  font-size: 11px;
  font-family: 'IBM Plex Mono', monospace;
  color: rgba(0, 238, 255, 0.4);
  pointer-events: none;
  line-height: 1.6;
}

.atlas-nav-hint strong {
  color: rgba(0, 238, 255, 0.7);
}

```

- [ ] **Step 3: Update the JSX hint**

Find the UNIVERSE level indicator in the JSX (search for `UNIVERSE`). Replace whatever hint is there with a more helpful version. Find:

```
UNIVERSE
```

This will be in a `<div>` — update it to show helpful navigation instructions. The exact JSX will be in the return section. Find the bottom-left hint element and replace the content with:

```
LEVEL {zoomLevel}/4 · {levelName}
Scroll to zoom · Click to explore · Right-drag to orbit
```

Where `levelName` maps 1→UNIVERSE, 2→GALAXY, 3→STAR SYSTEM, 4→PLANET.

- [ ] **Step 4: Build and commit**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
git add frontend/src/pages/Atlas3DPage.tsx frontend/src/styles.css
git commit -m "feat(atlas): bigger labels, navigation hint overlay"
```

---

### Task 7: Build, sync, and push

- [ ] **Step 1: Final build and sync**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build && cp dist/index.html ../src/copyclip/intelligence/ui/index.html
```

- [ ] **Step 2: Commit and push**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
git add src/copyclip/intelligence/ui/index.html
git commit -m "build(ui): sync atlas bundle with visual polish"
git push origin main
```
