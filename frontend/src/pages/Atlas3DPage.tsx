import { useEffect, useRef, useState, useCallback } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
// @ts-ignore — d3-force-3d has no type declarations
import { forceSimulation, forceManyBody, forceCenter, forceCollide } from 'd3-force-3d'
import { api } from '../api/client'
import type { TreeNode, SymbolItem, ModuleSourceFile } from '../types/api'

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

type ZoomLevel = 1 | 2 | 3 | 4

/** Metadata we attach to every clickable Three.js mesh via userData */
type NodeMeta = {
  treeNode?: TreeNode
  symbol?: SymbolItem
  method?: string
  methodLineStart?: number
  methodLineEnd?: number
  level: ZoomLevel
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

const getDebtColor = (debt: number): number => {
  if (debt > 70) return 0xff3333
  if (debt > 40) return 0xffaa00
  return 0x00eeff
}

const getDebtCSS = (debt: number): string => {
  if (debt > 70) return '#ff3333'
  if (debt > 40) return '#ffaa00'
  return '#00eeff'
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

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

/** Create a HUD label Sprite that always faces the camera. */
const createHUDLabel = (lines: string[], debtValue?: number): THREE.Sprite => {
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')!
  canvas.width = 512
  canvas.height = 40 * lines.length + 16
  ctx.font = '300 34px IBM Plex Mono'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  lines.forEach((line, i) => {
    // Color the last token of the last line by debt if provided
    if (debtValue !== undefined && i === lines.length - 1 && line.includes('%')) {
      const parts = line.split(' ')
      const debtPart = parts.pop()!
      const rest = parts.join(' ')
      ctx.fillStyle = '#ffffff'
      ctx.fillText(rest + ' ', 256, 8 + i * 40)
      const restWidth = ctx.measureText(rest + ' ').width
      ctx.fillStyle = getDebtCSS(debtValue)
      ctx.fillText(debtPart, 256 + restWidth / 2, 8 + i * 40)
    } else {
      ctx.fillStyle = '#ffffff'
      ctx.fillText(line, 256, 8 + i * 40)
    }
  })
  const texture = new THREE.CanvasTexture(canvas)
  const mat = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    opacity: 0.75,
    sizeAttenuation: true,
    depthWrite: false,
  })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(200, 200 * (canvas.height / canvas.width), 1)
  return sprite
}

/** Run d3-force-3d on a list of items, return FLAT disc positions (Y compressed). */
const forceLayout = (count: number, sizeFn: (i: number) => number, spread: number): THREE.Vector3[] => {
  if (count === 0) return []
  const nodes = Array.from({ length: count }, (_, i) => ({ index: i, x: 0, y: 0, z: 0 }))
  const sim = forceSimulation(nodes, 3)
    .force('charge', forceManyBody().strength(-spread * 1.5))
    .force('center', forceCenter(0, 0, 0))
    .force('collide', forceCollide().radius((d: any) => sizeFn(d.index) + 8))
    .stop()
  for (let t = 0; t < 300; t++) sim.tick()
  // Normalize positions to fit within a reasonable radius
  let maxDist = 1
  nodes.forEach((n: any) => {
    const d = Math.sqrt(n.x * n.x + n.z * n.z) // ignore Y for normalization
    if (d > maxDist) maxDist = d
  })
  const scale = spread * 4 / maxDist
  // Flatten Y to 15% — disc shape, not sphere
  return nodes.map((n: any) => new THREE.Vector3(n.x * scale, n.y * scale * 0.15, n.z * scale))
}

/** Spread items in an orbit around center. */
const orbitLayout = (count: number, radius: number): THREE.Vector3[] => {
  const positions: THREE.Vector3[] = []
  for (let i = 0; i < count; i++) {
    const phi = Math.acos(-1 + (2 * i) / Math.max(count, 1))
    const theta = Math.sqrt(Math.max(count, 1) * Math.PI) * phi
    positions.push(new THREE.Vector3(
      radius * Math.cos(theta) * Math.sin(phi),
      radius * Math.sin(theta) * Math.sin(phi) * 0.6,
      radius * Math.cos(phi),
    ))
  }
  return positions
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function Atlas3DPage() {
  const containerRef = useRef<HTMLDivElement>(null)

  // Core state
  const [loading, setLoading] = useState(true)
  const [zoomLevel, setZoomLevel] = useState<ZoomLevel>(1)
  const [currentPath, setCurrentPath] = useState<string[]>([])
  const [tree, setTree] = useState<TreeNode | null>(null)
  const [currentNode, setCurrentNode] = useState<TreeNode | null>(null)
  const [selectedMeta, setSelectedMeta] = useState<NodeMeta | null>(null)
  const [hoveredMeta, setHoveredMeta] = useState<NodeMeta | null>(null)

  // Level 3/4 data
  const [symbols, setSymbols] = useState<SymbolItem[]>([])
  const [sourceFiles, setSourceFiles] = useState<ModuleSourceFile[]>([])
  const [activeFileIdx, setActiveFileIdx] = useState(0)
  const [loadingSource, setLoadingSource] = useState(false)

  // CodeMirror
  const codeMirrorRef = useRef<HTMLDivElement>(null)
  const cmInstanceRef = useRef<any>(null)

  // Three.js refs stored outside React state for the animation loop
  const threeRef = useRef<{
    scene: THREE.Scene
    camera: THREE.PerspectiveCamera
    renderer: THREE.WebGLRenderer
    controls: OrbitControls
    raycaster: THREE.Raycaster
    nodesGroup: THREE.Group
    starsGroup: THREE.Group
    animationId: number
    hoveredMesh: THREE.Mesh | null
    selectedMesh: THREE.Mesh | null
    transitioning: boolean
    zoomLevel: ZoomLevel
    currentNode: TreeNode | null
    tree: TreeNode | null
    symbols: SymbolItem[]
    currentPath: string[]
  } | null>(null)

  /* ---- Zoom navigation callbacks (memoized, used by wheel/click) ---- */

  const renderLevelRef = useRef<(level: ZoomLevel, node: TreeNode | null, syms?: SymbolItem[]) => void>(() => {})
  const zoomIntoRef = useRef<(meta: NodeMeta) => void>(() => {})
  const zoomOutRef = useRef<() => void>(() => {})

  /* ================================================================== */
  /*  Main Three.js useEffect                                           */
  /* ================================================================== */

  useEffect(() => {
    if (!containerRef.current) return
    const container = containerRef.current

    // ---- Scene setup ----
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x000000)
    scene.fog = new THREE.FogExp2(0x000000, 0.00015)

    const camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 1, 12000)
    camera.position.set(0, 300, 900)

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setSize(container.clientWidth, container.clientHeight)
    container.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.05
    controls.enableZoom = true    // default zoom works, wheel handler intercepts when hovering a node

    const raycaster = new THREE.Raycaster()
    const nodesGroup = new THREE.Group()
    const starsGroup = new THREE.Group()
    scene.add(nodesGroup)

    // ---- Lighting ----
    scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.5))
    const sun = new THREE.DirectionalLight(0xffffff, 2.0)
    sun.position.set(1000, 1000, 1000)
    scene.add(sun)
    const center = new THREE.PointLight(0x00f0ff, 1, 3000)
    scene.add(center)

    // ---- Starfield ----
    const starGeo = new THREE.BufferGeometry()
    const sp: number[] = [], sc: number[] = []
    for (let i = 0; i < 12000; i++) {
      sp.push(Math.random() * 8000 - 4000, Math.random() * 8000 - 4000, Math.random() * 8000 - 4000)
      const b = 0.7 + Math.random() * 0.3
      sc.push(b, b, b)
    }
    starGeo.setAttribute('position', new THREE.Float32BufferAttribute(sp, 3))
    starGeo.setAttribute('color', new THREE.Float32BufferAttribute(sc, 3))
    starsGroup.add(new THREE.Points(starGeo, new THREE.PointsMaterial({
      size: 2, vertexColors: true, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending,
    })))
    scene.add(starsGroup)

    // ---- Store refs ----
    const T = {
      scene, camera, renderer, controls, raycaster, nodesGroup, starsGroup,
      animationId: 0,
      hoveredMesh: null as THREE.Mesh | null,
      selectedMesh: null as THREE.Mesh | null,
      transitioning: false,
      zoomLevel: 1 as ZoomLevel,
      currentNode: null as TreeNode | null,
      tree: null as TreeNode | null,
      symbols: [] as SymbolItem[],
      currentPath: [] as string[],
    }
    threeRef.current = T

    /* ================================================================ */
    /*  Render-level functions                                          */
    /* ================================================================ */

    const clearNodes = () => {
      while (nodesGroup.children.length) {
        const c = nodesGroup.children[0]
        nodesGroup.remove(c)
        c.traverse((o: any) => {
          if (o.geometry) o.geometry.dispose()
          if (o.material) {
            if (o.material.map) o.material.map.dispose()
            o.material.dispose()
          }
        })
      }
    }

    /** Build a mesh for a node and add to nodesGroup */
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

    /* ---------- Level 1: Universe (top-level folders as diamonds) ---- */
    const renderLevel1 = (root: TreeNode) => {
      clearNodes()
      const children = (root.children || []).filter(c => c.type === 'folder')
      if (children.length === 0 && root.children) {
        renderLevel2(root)
        return
      }
      const sizes = children.map(c => clamp(Math.log2((c.file_count || 1) + 1) * 8, 8, 50))
      const positions = forceLayout(children.length, i => sizes[i], 250)

      children.forEach((child, i) => {
        const debt = child.avg_debt || 0
        const geo = new THREE.OctahedronGeometry(sizes[i], 0)
        const lbl = createHUDLabel(
          [child.name, `${child.file_count || 0} files  ${Math.round(debt)}%`],
          debt,
        )
        addNodeMesh(geo, getNodeColor(child.name, debt), positions[i], lbl, { treeNode: child, level: 1 }, -(sizes[i] + 18))
      })

      camera.position.set(0, 500, 1500)
      controls.target.set(0, 0, 0)
    }

    /* ---------- Level 2: Galaxy (files as spheres, sub-folders as diamonds) */
    const renderLevel2 = (folder: TreeNode) => {
      clearNodes()
      const children = folder.children || []
      // Adaptive sizing: shrink nodes when there are many
      const scaleFactor = children.length > 50 ? 0.5 : children.length > 20 ? 0.7 : 1.0
      const sizes = children.map(c =>
        c.type === 'file'
          ? clamp(Math.log2((c.lines || 100) + 1) * 2.5 * scaleFactor, 3, 25)
          : clamp(Math.log2((c.file_count || 1) + 1) * 5 * scaleFactor, 4, 20),
      )
      // More spread when there are many nodes
      const dynamicSpread = Math.max(200, children.length * 8)
      const positions = forceLayout(children.length, i => sizes[i], dynamicSpread)

      children.forEach((child, i) => {
        const debt = child.type === 'file' ? (child.debt || 0) : (child.avg_debt || 0)
        const color = child.type === 'file'
          ? getLanguageColor(child.language || 'other', debt)
          : getNodeColor(child.name, debt)
        const geo = child.type === 'file'
          ? new THREE.SphereGeometry(sizes[i], 24, 24)
          : new THREE.OctahedronGeometry(sizes[i], 0)
        const info = child.type === 'file'
          ? [`${child.name}`, `${child.lines || '?'} ln  ${Math.round(debt)}%`]
          : [`${child.name}`, `${child.file_count || 0} files  ${Math.round(debt)}%`]
        const lbl = createHUDLabel(info, debt)
        addNodeMesh(geo, color, positions[i], lbl, { treeNode: child, level: 2 }, -(sizes[i] + 16))
      })

      // Camera distance adapts to node count
      const camDist = Math.max(1000, dynamicSpread * 4)
      camera.position.set(0, camDist * 0.35, camDist)
      controls.target.set(0, 0, 0)
    }

    /* ---------- Level 3: Star System (classes as cones, functions as cubes) */
    const renderLevel3 = (file: TreeNode, syms: SymbolItem[]) => {
      clearNodes()
      const classes = syms.filter(s => s.kind === 'class' || s.kind === 'struct' || s.kind === 'interface')
      const functions = syms.filter(s => s.kind === 'function')
      const allItems = [...classes, ...functions]
      if (allItems.length === 0) {
        // Nothing to show — put a single sphere representing the file
        const geo = new THREE.SphereGeometry(15, 24, 24)
        const lbl = createHUDLabel([file.name, 'no symbols found'])
        addNodeMesh(geo, getDebtColor(file.debt || 0), new THREE.Vector3(0, 0, 0), lbl, { treeNode: file, level: 3 }, -25)
        camera.position.set(0, 100, 300)
        controls.target.set(0, 0, 0)
        return
      }

      const sizes = allItems.map(s => {
        if (s.kind === 'class' || s.kind === 'struct' || s.kind === 'interface') {
          return clamp((s.methods?.length || 1) * 3, 8, 30)
        }
        return clamp(Math.sqrt((s.line_end || 0) - (s.line_start || 0) + 1) * 2, 6, 20)
      })
      const positions = forceLayout(allItems.length, i => sizes[i], 50)

      allItems.forEach((sym, i) => {
        const isClass = sym.kind === 'class' || sym.kind === 'struct' || sym.kind === 'interface'
        const geo = isClass
          ? new THREE.ConeGeometry(sizes[i], sizes[i] * 1.5, 4)
          : new THREE.BoxGeometry(sizes[i], sizes[i], sizes[i])
        const debt = file.debt || 0
        const info = isClass
          ? [sym.name, `${sym.kind}  ${sym.methods?.length || 0} methods`]
          : [sym.name, `function  ln ${sym.line_start}-${sym.line_end}`]
        const lbl = createHUDLabel(info)
        addNodeMesh(geo, getDebtColor(debt), positions[i], lbl, { symbol: sym, treeNode: file, level: 3 }, -(sizes[i] + 16))
      })

      camera.position.set(0, 150, 450)
      controls.target.set(0, 0, 0)
    }

    /* ---------- Level 4: Planet Detail (methods as small cubes) -------- */
    const renderLevel4 = (classSym: SymbolItem, file: TreeNode, syms: SymbolItem[]) => {
      clearNodes()
      const methods = classSym.methods || []
      if (methods.length === 0) {
        const geo = new THREE.ConeGeometry(12, 18, 4)
        const lbl = createHUDLabel([classSym.name, 'no methods'])
        addNodeMesh(geo, getDebtColor(file.debt || 0), new THREE.Vector3(0, 0, 0), lbl, { symbol: classSym, treeNode: file, level: 4 }, -22)
        camera.position.set(0, 80, 200)
        controls.target.set(0, 0, 0)
        return
      }

      // Find matching method symbols for line ranges
      const methodSyms = methods.map(m => syms.find(s => s.name === m && s.kind === 'method'))

      const radius = clamp(methods.length * 12, 40, 200)
      const positions = orbitLayout(methods.length, radius)

      methods.forEach((mName, i) => {
        const mSym = methodSyms[i]
        const size = mSym ? clamp(Math.sqrt((mSym.line_end - mSym.line_start) + 1) * 2, 5, 16) : 7
        const geo = new THREE.BoxGeometry(size, size, size)
        const info = mSym
          ? [mName, `ln ${mSym.line_start}-${mSym.line_end}`]
          : [mName, 'method']
        const lbl = createHUDLabel(info)
        addNodeMesh(geo, getDebtColor(file.debt || 0), positions[i], lbl,
          { method: mName, methodLineStart: mSym?.line_start, methodLineEnd: mSym?.line_end, symbol: classSym, treeNode: file, level: 4 },
          -(size + 14))
      })

      // Add central class cone
      const centerGeo = new THREE.ConeGeometry(10, 15, 4)
      const centerLbl = createHUDLabel([classSym.name, `${methods.length} methods`])
      addNodeMesh(centerGeo, getDebtColor(file.debt || 0), new THREE.Vector3(0, 0, 0), centerLbl,
        { symbol: classSym, treeNode: file, level: 4 }, -20)

      camera.position.set(0, 100, 300)
      controls.target.set(0, 0, 0)
    }

    /* ---------- Dispatch render ---------------------------------------- */
    const renderLevel = (level: ZoomLevel, node: TreeNode | null, syms?: SymbolItem[]) => {
      if (!node && level === 1) node = T.tree
      if (!node) return
      T.zoomLevel = level
      T.currentNode = node
      if (syms) T.symbols = syms

      switch (level) {
        case 1: renderLevel1(node); break
        case 2: renderLevel2(node); break
        case 3: renderLevel3(node, T.symbols); break
        case 4: {
          // node = file, find class from syms
          const classSym = syms?.[0]
          if (classSym) renderLevel4(classSym, node, T.symbols)
          break
        }
      }
    }
    renderLevelRef.current = renderLevel

    /* ================================================================ */
    /*  Transition animations                                           */
    /* ================================================================ */

    const expandInPlace = (callback: () => void) => {
      T.transitioning = true
      // Fade out all current nodes
      const meshes: THREE.Mesh[] = []
      nodesGroup.traverse(o => { if ((o as any).isMesh) meshes.push(o as THREE.Mesh) })

      let elapsed = 0
      const duration = 800
      const fadeOut = () => {
        elapsed += 16
        const t = Math.min(elapsed / duration, 1)
        const ease = 1 - Math.pow(1 - t, 3) // ease-out
        meshes.forEach(m => {
          const mat = m.material as THREE.MeshStandardMaterial
          mat.opacity = 1 - ease * 0.9
        })
        nodesGroup.children.forEach(g => {
          g.children.forEach(c => {
            if (c instanceof THREE.Sprite) {
              (c.material as THREE.SpriteMaterial).opacity = 0.75 * (1 - ease)
            }
          })
        })
        if (t < 1) {
          requestAnimationFrame(fadeOut)
        } else {
          callback()
          // Fade in new nodes
          const newMeshes: THREE.Mesh[] = []
          nodesGroup.traverse(o => { if ((o as any).isMesh) newMeshes.push(o as THREE.Mesh) })
          let el2 = 0
          const fadeIn = () => {
            el2 += 16
            const t2 = Math.min(el2 / 500, 1)
            newMeshes.forEach(m => {
              const mat = m.material as THREE.MeshStandardMaterial
              mat.opacity = t2
            })
            if (t2 < 1) requestAnimationFrame(fadeIn)
            else T.transitioning = false
          }
          fadeIn()
        }
      }
      fadeOut()
    }

    const flyThrough = (target: THREE.Vector3, callback: () => void) => {
      T.transitioning = true
      const startPos = camera.position.clone()
      const endPos = target.clone().add(new THREE.Vector3(0, 150, 450))
      let elapsed = 0
      const duration = 1500

      const step = () => {
        elapsed += 16
        const t = Math.min(elapsed / duration, 1)
        // ease-in-out
        const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2
        camera.position.lerpVectors(startPos, endPos, ease)

        // At 60%, fade out scene
        if (t > 0.6 && t < 0.8) {
          const fadeT = (t - 0.6) / 0.2
          nodesGroup.traverse(o => {
            if ((o as any).isMesh) {
              const mat = (o as THREE.Mesh).material as THREE.MeshStandardMaterial
              mat.opacity = 1 - fadeT
            }
          })
        }

        if (t >= 0.8 && t < 0.81) {
          // Switch scene content
          callback()
        }

        // At 80-100%, fade in new scene
        if (t >= 0.8) {
          const fadeT = (t - 0.8) / 0.2
          nodesGroup.traverse(o => {
            if ((o as any).isMesh) {
              const mat = (o as THREE.Mesh).material as THREE.MeshStandardMaterial
              mat.opacity = fadeT
            }
          })
        }

        if (t < 1) {
          requestAnimationFrame(step)
        } else {
          T.transitioning = false
        }
      }
      step()
    }

    /* ================================================================ */
    /*  Zoom into / out                                                 */
    /* ================================================================ */

    const zoomInto = async (meta: NodeMeta) => {
      if (T.transitioning) return
      const tn = meta.treeNode

      if (meta.level === 1 && tn && tn.type === 'folder') {
        // Level 1 -> 2: expand in place
        const newPath = [...T.currentPath, tn.name]
        expandInPlace(() => renderLevel(2, tn))
        T.currentPath = newPath
        setZoomLevel(2)
        setCurrentPath(newPath)
        setCurrentNode(tn)
        setSelectedMeta(null)
        setHoveredMeta(null)
      } else if (meta.level === 2 && tn) {
        if (tn.type === 'folder') {
          // Sub-folder click at Level 2: stay Level 2, open the sub-folder
          const newPath = [...T.currentPath, tn.name]
          expandInPlace(() => renderLevel(2, tn))
          T.currentPath = newPath
          setCurrentPath(newPath)
          setCurrentNode(tn)
          setSelectedMeta(null)
          setHoveredMeta(null)
        } else if (tn.type === 'file') {
          // Level 2 -> 3: cinematic fly-through
          const newPath = [...T.currentPath, tn.name]
          setLoadingSource(true)
          try {
            // Derive the module path for the API call: parent folder path
            const filePath = tn.path
            const modulePath = filePath.includes('/') ? filePath.substring(0, filePath.lastIndexOf('/')) : 'root'
            const [symsRes, srcRes] = await Promise.all([
              api.moduleSymbols(modulePath),
              api.moduleSource(modulePath),
            ])
            const syms = (symsRes.symbols || []).filter(s => s.file_path === tn.path)
            const srcs = srcRes.files || []
            T.symbols = syms
            setSymbols(syms)
            setSourceFiles(srcs)
            setActiveFileIdx(srcs.findIndex(f => f.path === tn.path) >= 0 ? srcs.findIndex(f => f.path === tn.path) : 0)
            setLoadingSource(false)

            // Find mesh position for fly-through target
            let targetPos = new THREE.Vector3(0, 0, 0)
            nodesGroup.children.forEach(g => {
              const mesh = g.children.find(c => (c as any).isMesh) as THREE.Mesh | undefined
              if (mesh && mesh.userData?.treeNode?.path === tn.path) {
                targetPos = g.position.clone()
              }
            })

            flyThrough(targetPos, () => renderLevel(3, tn, syms))
            T.currentPath = newPath
            setZoomLevel(3)
            setCurrentPath(newPath)
            setCurrentNode(tn)
            setSelectedMeta(null)
            setHoveredMeta(null)
          } catch (e) {
            console.error('Failed to load symbols for Level 3', e)
            setLoadingSource(false)
          }
        }
      } else if (meta.level === 3 && meta.symbol) {
        // Level 3 -> 4: expand in place for class with methods
        const sym = meta.symbol
        if ((sym.kind === 'class' || sym.kind === 'struct' || sym.kind === 'interface') && sym.methods && sym.methods.length > 0) {
          const newPath = [...T.currentPath, sym.name]
          expandInPlace(() => renderLevel(4, meta.treeNode!, [sym]))
          T.currentPath = newPath
          setZoomLevel(4)
          setCurrentPath(newPath)
          setSelectedMeta(null)
          setHoveredMeta(null)
        } else {
          // Function click at Level 3 — select it to show code
          setSelectedMeta(meta)
          if (meta.symbol && cmInstanceRef.current && meta.symbol.line_start) {
            setTimeout(() => cmInstanceRef.current?.scrollIntoView({ line: meta.symbol!.line_start - 1, ch: 0 }), 100)
          }
        }
      } else if (meta.level === 4 && meta.method) {
        // Method click — select to show in CodeMirror
        setSelectedMeta(meta)
        if (meta.methodLineStart && cmInstanceRef.current) {
          setTimeout(() => cmInstanceRef.current?.scrollIntoView({ line: meta.methodLineStart! - 1, ch: 0 }), 100)
        }
      }
    }
    zoomIntoRef.current = zoomInto

    const zoomOut = () => {
      if (T.transitioning) return
      if (T.zoomLevel <= 1) return

      const newLevel = (T.zoomLevel === 4 ? 3 : T.zoomLevel === 3 ? 2 : 1) as ZoomLevel
      const newPath = [...T.currentPath]
      newPath.pop()
      T.currentPath = newPath

      if (newLevel === 1) {
        expandInPlace(() => renderLevel(1, T.tree))
        setZoomLevel(1)
        setCurrentPath([])
        setCurrentNode(T.tree)
        setSelectedMeta(null)
        setHoveredMeta(null)
        setSymbols([])
        setSourceFiles([])
      } else if (newLevel === 2) {
        // Go back to the parent folder
        const parentNode = findNodeByPath(T.tree!, newPath)
        expandInPlace(() => renderLevel(2, parentNode || T.tree))
        setZoomLevel(2)
        setCurrentPath(newPath)
        setCurrentNode(parentNode || T.tree)
        setSelectedMeta(null)
        setHoveredMeta(null)
        setSymbols([])
        setSourceFiles([])
      } else if (newLevel === 3) {
        // Back from Level 4 to Level 3
        expandInPlace(() => renderLevel(3, T.currentNode, T.symbols))
        setZoomLevel(3)
        setCurrentPath(newPath)
        setSelectedMeta(null)
        setHoveredMeta(null)
      }
    }
    zoomOutRef.current = zoomOut

    /** Walk the tree following a path of names. */
    const findNodeByPath = (root: TreeNode, path: string[]): TreeNode | null => {
      let node: TreeNode | null = root
      for (const seg of path) {
        if (!node || !node.children) return null
        const found: TreeNode | undefined = node.children.find(c => c.name === seg)
        if (!found) return null
        node = found
      }
      return node
    }

    /* ================================================================ */
    /*  Event handlers                                                  */
    /* ================================================================ */

    const mouse = new THREE.Vector2()

    const getMeshUnderMouse = (event: MouseEvent): THREE.Mesh | null => {
      const rect = renderer.domElement.getBoundingClientRect()
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera(mouse, camera)
      const hits = raycaster.intersectObjects(nodesGroup.children, true)
      const hit = hits.find(h => (h.object as any).isMesh && (h.object as THREE.Mesh).userData?.level && !(h.object as THREE.Mesh).userData?._glow)
      return hit ? hit.object as THREE.Mesh : null
    }

    const onMouseMove = (event: MouseEvent) => {
      const mesh = getMeshUnderMouse(event)
      if (mesh) {
        if (T.hoveredMesh !== mesh) {
          // Reset previous
          if (T.hoveredMesh && T.hoveredMesh !== T.selectedMesh) {
            const mat = T.hoveredMesh.material as THREE.MeshStandardMaterial
            mat.emissiveIntensity = 0.4
          }
          T.hoveredMesh = mesh
          const mat = mesh.material as THREE.MeshStandardMaterial
          mat.emissiveIntensity = 1.0
          // Dim other nodes
          nodesGroup.children.forEach(g => {
            const m = g.children.find(c => (c as any).isMesh && (c as THREE.Mesh).userData?.level && !(c as THREE.Mesh).userData?._glow) as THREE.Mesh | undefined
            if (m && m !== mesh) {
              const mmat = m.material as THREE.MeshStandardMaterial
              mmat.opacity = 0.2
              mmat.emissiveIntensity = 0.1
            }
          })
          setHoveredMeta(mesh.userData as NodeMeta)
        }
        renderer.domElement.style.cursor = 'pointer'
      } else {
        if (T.hoveredMesh && T.hoveredMesh !== T.selectedMesh) {
          const mat = T.hoveredMesh.material as THREE.MeshStandardMaterial
          mat.emissiveIntensity = 0.4
        }
        T.hoveredMesh = null
        // Restore all nodes
        nodesGroup.children.forEach(g => {
          const m = g.children.find(c => (c as any).isMesh && (c as THREE.Mesh).userData?.level && !(c as THREE.Mesh).userData?._glow) as THREE.Mesh | undefined
          if (m && m !== T.selectedMesh) {
            const mmat = m.material as THREE.MeshStandardMaterial
            mmat.opacity = 1.0
            mmat.emissiveIntensity = 0.4
          }
        })
        setHoveredMeta(null)
        renderer.domElement.style.cursor = 'default'
      }
    }

    const onClick = (event: MouseEvent) => {
      if (T.transitioning) return
      const mesh = getMeshUnderMouse(event)
      if (mesh) {
        const meta = mesh.userData as NodeMeta
        // Reset previous selection visual
        if (T.selectedMesh) {
          const pm = T.selectedMesh.material as THREE.MeshStandardMaterial
          pm.emissiveIntensity = 0.3
        }
        T.selectedMesh = mesh
        const mat = mesh.material as THREE.MeshStandardMaterial
        mat.emissiveIntensity = 1.5
        setSelectedMeta(meta)
      } else {
        // Click on deep space — zoom out one level
        if (T.selectedMesh) {
          const pm = T.selectedMesh.material as THREE.MeshStandardMaterial
          pm.emissiveIntensity = 0.3
          T.selectedMesh = null
          setSelectedMeta(null)
        }
        if (T.zoomLevel > 1) {
          zoomOut()
        } else {
          setSelectedMeta(null)
        }
      }
    }

    const onWheel = (event: WheelEvent) => {
      if (T.transitioning) return

      // Only intercept scroll when directly hovering a node — otherwise let OrbitControls zoom
      if (T.hoveredMesh && event.deltaY < 0) {
        event.preventDefault()
        event.stopPropagation()
        const meta = T.hoveredMesh.userData as NodeMeta
        zoomInto(meta)
      }
      // Scroll out only at deeper levels, not at Level 1
      // At Level 1, scroll out = normal camera zoom (OrbitControls handles it)
    }

    const onResize = () => {
      if (!container) return
      camera.aspect = container.clientWidth / container.clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(container.clientWidth, container.clientHeight)
    }

    // ---- Attach events ----
    renderer.domElement.addEventListener('wheel', onWheel)
    renderer.domElement.addEventListener('mousemove', onMouseMove)
    renderer.domElement.addEventListener('click', onClick)
    window.addEventListener('resize', onResize)

    /* ================================================================ */
    /*  Animation loop                                                  */
    /* ================================================================ */

    const animate = () => {
      T.animationId = requestAnimationFrame(animate)
      controls.update()
      starsGroup.rotation.y += 0.0001

      // Lerp node scale on hover/select
      nodesGroup.children.forEach(g => {
        const mesh = g.children.find(c => (c as any).isMesh) as THREE.Mesh | undefined
        if (!mesh) return
        const isHovered = T.hoveredMesh === mesh
        const isSelected = T.selectedMesh === mesh
        const ts = isSelected ? 1.8 : isHovered ? 1.3 : 1.0
        mesh.scale.lerp(new THREE.Vector3(ts, ts, ts), 0.1)
      })

      // Distance-based label opacity
      if (!T.hoveredMesh && !T.selectedMesh) {
        nodesGroup.children.forEach(g => {
          const label = g.children.find(c => c instanceof THREE.Sprite) as THREE.Sprite | undefined
          if (!label) return
          const dist = camera.position.distanceTo(g.position)
          const op = clamp(1 - dist / 2500, 0.1, 0.9)
          ;(label.material as THREE.SpriteMaterial).opacity = op
        })
      }

      renderer.render(scene, camera)
    }

    /* ================================================================ */
    /*  Load tree data and kick off                                     */
    /* ================================================================ */

    api.architectureTree()
      .then(treeData => {
        T.tree = treeData
        setTree(treeData)
        setCurrentNode(treeData)
        renderLevel(1, treeData)
        setLoading(false)
      })
      .catch(err => {
        console.error('Failed to load architecture tree', err)
        setLoading(false)
      })

    animate()

    /* ---- Cleanup ---- */
    return () => {
      cancelAnimationFrame(T.animationId)
      renderer.domElement.removeEventListener('wheel', onWheel)
      renderer.domElement.removeEventListener('mousemove', onMouseMove)
      renderer.domElement.removeEventListener('click', onClick)
      window.removeEventListener('resize', onResize)
      renderer.dispose()
      while (container.firstChild) container.removeChild(container.firstChild)
      threeRef.current = null
    }
  }, [])

  /* ================================================================== */
  /*  CodeMirror integration (Levels 3 & 4)                             */
  /* ================================================================== */

  useEffect(() => {
    if (zoomLevel < 3 || sourceFiles.length === 0) return
    const file = sourceFiles[activeFileIdx]
    if (!file) return

    const timer = setTimeout(() => {
      const el = codeMirrorRef.current
      if (!el) return

      if (cmInstanceRef.current) {
        cmInstanceRef.current.toTextArea()
        cmInstanceRef.current = null
      }
      while (el.firstChild) el.removeChild(el.firstChild)
      const ta = document.createElement('textarea')
      el.appendChild(ta)

      const CM = (window as any).CodeMirror
      if (!CM) return
      cmInstanceRef.current = CM.fromTextArea(ta, {
        value: file.content,
        mode: file.language || null,
        readOnly: true,
        lineNumbers: true,
        theme: 'atlas-cosmic',
      })
      cmInstanceRef.current.setValue(file.content)
    }, 50)

    return () => clearTimeout(timer)
  }, [zoomLevel, sourceFiles, activeFileIdx])

  /* ================================================================== */
  /*  Breadcrumb navigation                                             */
  /* ================================================================== */

  const jumpToBreadcrumb = useCallback((index: number) => {
    const T = threeRef.current
    if (!T || !T.tree || T.transitioning) return

    if (index === -1) {
      // Jump to project root / Level 1
      T.currentPath = []
      T.zoomLevel = 1
      renderLevelRef.current(1, T.tree)
      setZoomLevel(1)
      setCurrentPath([])
      setCurrentNode(T.tree)
      setSelectedMeta(null)
      setSymbols([])
      setSourceFiles([])
      return
    }

    const newPath = currentPath.slice(0, index + 1)
    // Walk the tree to find the node
    let node: TreeNode | null = T.tree
    for (const seg of newPath) {
      if (!node || !node.children) break
      node = node.children.find(c => c.name === seg) || null
    }
    if (!node) return

    const level = (node.type === 'file' ? 3 : Math.min(index + 2, 2)) as ZoomLevel
    T.currentPath = newPath
    T.zoomLevel = level
    if (level <= 2) {
      renderLevelRef.current(level, node)
      setSymbols([])
      setSourceFiles([])
    }
    setZoomLevel(level)
    setCurrentPath(newPath)
    setCurrentNode(node)
    setSelectedMeta(null)
  }, [currentPath])

  /* ================================================================== */
  /*  Detail panel content                                              */
  /* ================================================================== */

  const activeMeta = selectedMeta || hoveredMeta

  const renderPanelContent = () => {
    if (!activeMeta) return null

    if (activeMeta.level === 1 && activeMeta.treeNode) {
      const n = activeMeta.treeNode
      return (
        <>
          <div style={{ fontSize: 18, color: '#fff', marginBottom: 16, fontWeight: 500 }}>{n.name}</div>
          <div className="panel" style={{ padding: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid #222', marginBottom: 8 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12 }}>
              <div><span style={{ color: '#666' }}>FILES</span></div><div style={{ color: '#fff' }}>{n.file_count || 0}</div>
              <div><span style={{ color: '#666' }}>AVG DEBT</span></div><div style={{ color: getDebtCSS(n.avg_debt || 0) }}>{Math.round(n.avg_debt || 0)}%</div>
            </div>
          </div>
          {n.children && n.children.length > 0 && (
            <div style={{ fontSize: 10, color: '#666', marginTop: 8 }}>
              {n.children.filter(c => c.type === 'folder').length} sub-folders, {n.children.filter(c => c.type === 'file').length} files
            </div>
          )}
          <div style={{ fontSize: 11, color: '#00eeff', opacity: 0.6, marginTop: 12 }}>Click or scroll to enter</div>
        </>
      )
    }

    if (activeMeta.level === 2 && activeMeta.treeNode) {
      const n = activeMeta.treeNode
      if (n.type === 'file') {
        return (
          <>
            <div style={{ fontSize: 18, color: '#fff', marginBottom: 16, fontWeight: 500 }}>{n.name}</div>
            <div className="panel" style={{ padding: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid #222', marginBottom: 8 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12 }}>
                <div><span style={{ color: '#666' }}>LINES</span></div><div style={{ color: '#fff' }}>{n.lines?.toLocaleString() || '?'}</div>
                <div><span style={{ color: '#666' }}>DEBT</span></div><div style={{ color: getDebtCSS(n.debt || 0) }}>{Math.round(n.debt || 0)}%</div>
                <div><span style={{ color: '#666' }}>SYMBOLS</span></div><div style={{ color: '#fff' }}>{n.symbol_count || 0}</div>
                {n.language && <><div><span style={{ color: '#666' }}>LANGUAGE</span></div><div style={{ color: '#fff' }}>{n.language}</div></>}
              </div>
            </div>
            <div style={{ fontSize: 11, color: '#00eeff', opacity: 0.6, marginTop: 12 }}>Click or scroll to enter</div>
          </>
        )
      }
      // Sub-folder at Level 2
      return (
        <>
          <div style={{ fontSize: 18, color: '#fff', marginBottom: 16, fontWeight: 500 }}>{n.name}</div>
          <div className="panel" style={{ padding: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid #222', marginBottom: 8 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12 }}>
              <div><span style={{ color: '#666' }}>FILES</span></div><div style={{ color: '#fff' }}>{n.file_count || 0}</div>
              <div><span style={{ color: '#666' }}>AVG DEBT</span></div><div style={{ color: getDebtCSS(n.avg_debt || 0) }}>{Math.round(n.avg_debt || 0)}%</div>
            </div>
          </div>
          <div style={{ fontSize: 11, color: '#00eeff', opacity: 0.6, marginTop: 12 }}>Click to expand</div>
        </>
      )
    }

    if (activeMeta.level === 3 && activeMeta.symbol) {
      const sym = activeMeta.symbol
      const isClass = sym.kind === 'class' || sym.kind === 'struct' || sym.kind === 'interface'
      return (
        <>
          <div style={{ fontSize: 18, color: '#fff', marginBottom: 16, fontWeight: 500 }}>{sym.name}</div>
          <div className="panel" style={{ padding: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid #222', marginBottom: 8 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12 }}>
              <div><span style={{ color: '#666' }}>KIND</span></div><div style={{ color: '#fff' }}>{sym.kind}</div>
              <div><span style={{ color: '#666' }}>LINES</span></div><div style={{ color: '#fff' }}>{sym.line_start}-{sym.line_end}</div>
              {isClass && sym.methods && <><div><span style={{ color: '#666' }}>METHODS</span></div><div style={{ color: '#fff' }}>{sym.methods.length}</div></>}
              {sym.inherits && sym.inherits.length > 0 && <><div><span style={{ color: '#666' }}>INHERITS</span></div><div style={{ color: '#00eeff' }}>{sym.inherits.join(', ')}</div></>}
            </div>
          </div>
          {sym.calls && sym.calls.length > 0 && (
            <div style={{ fontSize: 10, color: '#666', marginTop: 8 }}>
              CALLS: <span style={{ color: '#888' }}>{sym.calls.slice(0, 5).join(', ')}{sym.calls.length > 5 ? '...' : ''}</span>
            </div>
          )}
          {sym.called_by && sym.called_by.length > 0 && (
            <div style={{ fontSize: 10, color: '#666', marginTop: 4 }}>
              CALLED BY: <span style={{ color: '#888' }}>{sym.called_by.slice(0, 5).join(', ')}</span>
            </div>
          )}
          {isClass && sym.methods && sym.methods.length > 0 && (
            <div style={{ fontSize: 11, color: '#00eeff', opacity: 0.6, marginTop: 12 }}>Click or scroll to see methods</div>
          )}
        </>
      )
    }

    if (activeMeta.level === 4) {
      if (activeMeta.method) {
        return (
          <>
            <div style={{ fontSize: 18, color: '#fff', marginBottom: 16, fontWeight: 500 }}>{activeMeta.method}</div>
            <div className="panel" style={{ padding: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid #222', marginBottom: 8 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12 }}>
                <div><span style={{ color: '#666' }}>KIND</span></div><div style={{ color: '#fff' }}>method</div>
                {activeMeta.methodLineStart && (
                  <><div><span style={{ color: '#666' }}>LINES</span></div><div style={{ color: '#fff' }}>{activeMeta.methodLineStart}-{activeMeta.methodLineEnd}</div></>
                )}
              </div>
            </div>
          </>
        )
      }
      if (activeMeta.symbol) {
        return (
          <>
            <div style={{ fontSize: 18, color: '#fff', marginBottom: 16, fontWeight: 500 }}>{activeMeta.symbol.name}</div>
            <div style={{ fontSize: 12, color: '#666' }}>{activeMeta.symbol.kind} with {activeMeta.symbol.methods?.length || 0} methods</div>
          </>
        )
      }
    }

    return null
  }

  /* ================================================================== */
  /*  Double-click to zoom into selected                                */
  /* ================================================================== */

  const handlePanelDoubleClick = useCallback(() => {
    if (!selectedMeta) return
    zoomIntoRef.current(selectedMeta)
  }, [selectedMeta])

  /* ================================================================== */
  /*  JSX                                                               */
  /* ================================================================== */

  return (
    <div style={{ position: 'relative', width: '100%', height: 'calc(100vh - 100px)', background: '#000', borderRadius: 12, overflow: 'hidden' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

      {/* Header */}
      <div style={{ position: 'absolute', top: 30, left: 30, pointerEvents: 'none' }}>
        <div style={{ fontSize: 10, color: '#666', letterSpacing: 3, textTransform: 'uppercase', marginBottom: 4 }}>// cosmic_project_atlas</div>
        <div style={{ fontSize: 24, color: '#fff', fontWeight: 300 }}>The Atlas</div>
      </div>

      {/* Breadcrumb */}
      {currentPath.length > 0 && (
        <div className="atlas-breadcrumb">
          <span
            className={`atlas-breadcrumb-segment${zoomLevel === 1 ? ' atlas-breadcrumb-segment--active' : ''}`}
            onClick={() => jumpToBreadcrumb(-1)}
          >
            project
          </span>
          {currentPath.map((seg, i) => (
            <span key={i}>
              <span className="atlas-breadcrumb-separator">&gt;</span>
              <span
                className={`atlas-breadcrumb-segment${i === currentPath.length - 1 ? ' atlas-breadcrumb-segment--active' : ''}`}
                onClick={() => jumpToBreadcrumb(i)}
              >
                {seg}
              </span>
            </span>
          ))}
        </div>
      )}

      {/* Zoom level indicator */}
      <div className="atlas-nav-hint">
        <div>
          <strong>LEVEL {zoomLevel}/4 · {
            zoomLevel === 1 ? 'UNIVERSE' :
            zoomLevel === 2 ? 'GALAXY' :
            zoomLevel === 3 ? 'STAR SYSTEM' : 'PLANET'
          }</strong>
        </div>
        <div>Scroll to zoom · Click to explore · Right-drag to orbit</div>
      </div>

      {/* Detail panel */}
      {activeMeta && (
        <div
          data-augmented-ui=""
          className={`atlas-info-panel${selectedMeta ? ' atlas-info-panel--locked' : ''}`}
          onDoubleClick={handlePanelDoubleClick}
        >
          <div style={{ fontSize: 9, color: selectedMeta ? '#00eeff' : '#666', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            {selectedMeta ? 'Persistent link established' : 'Reading project body\u2026'}
          </div>
          <div style={{ display: 'grid', gap: 12 }}>
            {renderPanelContent()}

            {/* CodeMirror for Level 3/4 when selected */}
            {selectedMeta && zoomLevel >= 3 && sourceFiles.length > 0 && (
              <>
                <div className="atlas-file-tabs">
                  {sourceFiles.map((f, i) => (
                    <div
                      key={f.path}
                      className={`atlas-file-tab${i === activeFileIdx ? ' atlas-file-tab--active' : ''}`}
                      onClick={() => setActiveFileIdx(i)}
                    >
                      {f.path.split('/').pop()}
                    </div>
                  ))}
                </div>
                <div className="atlas-code-container" ref={codeMirrorRef} />
              </>
            )}
            {selectedMeta && loadingSource && sourceFiles.length === 0 && (
              <div style={{ fontSize: 10, color: '#666', padding: 12 }}>Loading source...</div>
            )}
          </div>
          {selectedMeta && (
            <div style={{ fontSize: 11, color: '#00eeff', opacity: 0.6, marginTop: 8 }}>
              {zoomLevel < 4 ? 'Double-click panel or scroll in to go deeper. Click deep space to go back.' : 'Click deep space to go back.'}
            </div>
          )}
        </div>
      )}

      {/* Loading overlay */}
      {loading && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#fff', letterSpacing: 4, fontWeight: 200 }}>
          MATERIALIZING THE ATLAS{'\u2026'}
        </div>
      )}
    </div>
  )
}
