import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { api } from '../api/client'
import type { ArchNode, ArchEdge, CognitiveLoadItem } from '../types/api'

type ViewMode = 'constellation' | 'tree'
type ColorMode = 'default' | 'cognitive'

interface TreeNode {
  name: string
  fullName: string
  children: Record<string, TreeNode>
  isModule: boolean
  depth: number
  position?: THREE.Vector3
  debt?: number
}

export function Atlas3DPage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState<any>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('tree')
  const [colorMode, setColorMode] = useState<ColorMode>('default')

  const sceneRef = useRef<THREE.Scene | null>(null)
  const spheresRef = useRef<THREE.Mesh[]>([])

  useEffect(() => {
    if (!containerRef.current) return

    let scene: THREE.Scene, camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer, controls: OrbitControls
    let raycaster: THREE.Raycaster, mouse: THREE.Vector2
    let animationId: number
    const graphGroup = new THREE.Group()

    const init = async () => {
      scene = new THREE.Scene()
      sceneRef.current = scene
      scene.background = new THREE.Color(0x030305)
      scene.fog = new THREE.FogExp2(0x030305, 0.001)

      camera = new THREE.PerspectiveCamera(70, containerRef.current!.clientWidth / containerRef.current!.clientHeight, 1, 4000)
      camera.position.set(400, 400, 800)

      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
      renderer.setSize(containerRef.current!.clientWidth, containerRef.current!.clientHeight)
      renderer.setPixelRatio(window.devicePixelRatio)
      containerRef.current!.appendChild(renderer.domElement)

      controls = new OrbitControls(camera, renderer.domElement)
      controls.enableDamping = true

      raycaster = new THREE.Raycaster()
      mouse = new THREE.Vector2()

      scene.add(new THREE.AmbientLight(0xffffff, 0.3))
      const light = new THREE.DirectionalLight(0xffffff, 0.8)
      light.position.set(1, 1, 1)
      scene.add(light)

      try {
        const [{ nodes, edges }, cog] = await Promise.all([
          api.architecture(),
          api.cognitiveLoad()
        ])
        
        buildAndRender(nodes, edges, cog.items || [])
        setLoading(false)
      } catch (e) {
        console.error(e)
      }

      scene.add(graphGroup)
      animate()

      renderer.domElement.addEventListener('click', (e) => {
        const rect = renderer.domElement.getBoundingClientRect()
        mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
        mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
        raycaster.setFromCamera(mouse, camera)
        const intersects = raycaster.intersectObjects(graphGroup.children, true)
        if (intersects.length > 0) {
          const mesh = intersects[0].object as THREE.Mesh
          if (mesh.userData?.name) {
            setSelectedNode(mesh.userData)
            spheresRef.current.forEach(s => (s.material as any).emissiveIntensity = 0.1)
            ;(mesh.material as any).emissiveIntensity = 1.5
          }
        } else {
          setSelectedNode(null)
        }
      })
    }

    const buildAndRender = (nodes: ArchNode[], edges: ArchEdge[], cogItems: CognitiveLoadItem[]) => {
      graphGroup.clear()
      spheresRef.current = []
      
      if (viewMode === 'tree') {
        renderSittingTree(nodes, cogItems)
      } else {
        renderConstellation(nodes, edges, cogItems)
      }
    }

    const renderSittingTree = (nodes: ArchNode[], cogItems: CognitiveLoadItem[]) => {
      const root: TreeNode = { name: 'root', fullName: 'root', children: {}, isModule: false, depth: 0 }
      
      // 1. Build hierarchy from paths (names usually contain folder structure)
      nodes.forEach(n => {
        const parts = n.name.split('/')
        let curr = root
        parts.forEach((part, idx) => {
          if (!curr.children[part]) {
            curr.children[part] = { 
              name: part, 
              fullName: parts.slice(0, idx + 1).join('/'),
              children: {}, 
              isModule: idx === parts.length - 1,
              depth: idx + 1
            }
          }
          curr = curr.children[part]
        })
      })

      // 2. Recursive Position Assignment (Radial Tree)
      const assignPositions = (node: TreeNode, angleStart: number, angleEnd: number, parentPos: THREE.Vector3) => {
        const radius = node.depth * 180
        const angle = (angleStart + angleEnd) / 2
        const x = Math.cos(angle) * radius
        const z = Math.sin(angle) * radius
        const y = node.depth * 100 // Height increases with depth
        
        node.position = new THREE.Vector3(x, y, z)
        
        // Render Node
        const cog = cogItems.find(c => c.module === node.fullName)
        const debt = cog?.cognitive_debt_score || 0
        const color = getDebtColor(debt)
        
        const geo = node.isModule ? new THREE.SphereGeometry(8 + (debt/10), 20, 20) : new THREE.BoxGeometry(10, 10, 10)
        const mat = new THREE.MeshPhongMaterial({ 
          color: node.isModule ? 0x06b6d4 : 0x444444, 
          emissive: node.isModule ? 0x06b6d4 : 0x000000,
          emissiveIntensity: 0.2 
        })
        const mesh = new THREE.Mesh(geo, mat)
        mesh.position.copy(node.position)
        mesh.userData = { ...node, debt }
        graphGroup.add(mesh)
        if (node.isModule) spheresRef.current.push(mesh)

        // Render Branch to parent
        if (node.depth > 0) {
          const lineGeo = new THREE.BufferGeometry().setFromPoints([parentPos, node.position])
          const lineMat = new THREE.LineBasicMaterial({ color: 0x222222, transparent: true, opacity: 0.4 })
          graphGroup.add(new THREE.Line(lineGeo, lineMat))
        }

        // Children expansion
        const childKeys = Object.keys(node.children)
        const step = (angleEnd - angleStart) / (childKeys.length || 1)
        childKeys.forEach((key, i) => {
          assignPositions(node.children[key], angleStart + i * step, angleStart + (i + 1) * step, node.position!)
        })
      }

      assignPositions(root, 0, Math.PI * 2, new THREE.Vector3(0, 0, 0))
    }

    const renderConstellation = (nodes: ArchNode[], edges: ArchEdge[], cogItems: CognitiveLoadItem[]) => {
      // (Legacy spherical code, but optimized)
      const nodeMap: Record<string, THREE.Vector3> = {}
      nodes.forEach((n, i) => {
        const phi = Math.acos(-1 + (2 * i) / nodes.length)
        const theta = Math.sqrt(nodes.length * Math.PI) * phi
        const pos = new THREE.Vector3(400 * Math.cos(theta) * Math.sin(phi), 400 * Math.sin(theta) * Math.sin(phi), 400 * Math.cos(phi))
        const cog = cogItems.find(c => c.module === n.name)
        const debt = cog?.cognitive_debt_score || 0
        const mesh = new THREE.Mesh(new THREE.SphereGeometry(6 + (debt/15)), new THREE.MeshPhongMaterial({ color: 0x06b6d4, emissive: 0x06b6d4, emissiveIntensity: 0.2 }))
        mesh.position.copy(pos)
        mesh.userData = { ...n, debt }
        graphGroup.add(mesh)
        spheresRef.current.push(mesh)
        nodeMap[n.name] = pos
      })
      edges.forEach(e => {
        if (nodeMap[e.from] && nodeMap[e.to]) {
          const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints([nodeMap[e.from], nodeMap[e.to]]), new THREE.LineBasicMaterial({ color: 0x222222, opacity: 0.2, transparent: true }))
          graphGroup.add(l)
        }
      })
    }

    const getDebtColor = (debt: number) => {
      if (debt > 70) return 0xef4444
      if (debt > 40) return 0xf59e0b
      return 0x10b981
    }

    const animate = () => {
      animationId = requestAnimationFrame(animate)
      controls.update()
      renderer.render(scene, camera)
    }

    init()
    return () => {
      cancelAnimationFrame(animationId)
      renderer.dispose()
      if (containerRef.current) containerRef.current.innerHTML = ''
    }
  }, [viewMode]) // Re-render when viewMode changes

  // Dynamic Coloring Effect
  useEffect(() => {
    spheresRef.current.forEach(s => {
      const debt = s.userData.debt || 0
      const mat = s.material as THREE.MeshPhongMaterial
      if (colorMode === 'cognitive') {
        if (debt > 70) mat.color.setHex(0xef4444)
        else if (debt > 40) mat.color.setHex(0xf59e0b)
        else mat.color.setHex(0x10b981)
      } else {
        mat.color.setHex(0x06b6d4)
      }
    })
  }, [colorMode])

  return (
    <div style={{ position: 'relative', width: '100%', height: 'calc(100vh - 100px)', background: '#030305', borderRadius: 12, overflow: 'hidden', border: '1px solid #111' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      
      {/* HUD: Mode Selectors */}
      <div style={{ position: 'absolute', top: 20, left: 20, display: 'grid', gap: 12 }}>
        <div style={{ display: 'flex', gap: 8, background: 'rgba(0,0,0,0.5)', padding: 4, borderRadius: 8, border: '1px solid #222' }}>
          <button className={`btn ${viewMode === 'tree' ? 'primary' : ''}`} onClick={() => setViewMode('tree')}>Sitting Tree</button>
          <button className={`btn ${viewMode === 'constellation' ? 'primary' : ''}`} onClick={() => setViewMode('constellation')}>Constellation</button>
        </div>
        <div style={{ display: 'flex', gap: 8, background: 'rgba(0,0,0,0.5)', padding: 4, borderRadius: 8, border: '1px solid #222' }}>
          <button className={`btn ${colorMode === 'default' ? 'primary' : ''}`} onClick={() => setColorMode('default')}>Standard</button>
          <button className={`btn ${colorMode === 'cognitive' ? 'primary' : ''}`} onClick={() => setColorMode('cognitive')}>Fog Heatmap</button>
        </div>
      </div>

      {/* Selected Node Overlay */}
      {selectedNode && (
        <div style={{ position: 'absolute', top: 20, right: 20, width: 260, background: 'rgba(5,5,10,0.9)', border: '1px solid var(--accent-cyan)', padding: 20, borderRadius: 8, backdropFilter: 'blur(10px)' }}>
          <div className="muted" style={{ fontSize: 9 }}>// node_focused</div>
          <div style={{ fontSize: 14, color: 'var(--accent-cyan)', margin: '8px 0' }}>{selectedNode.fullName}</div>
          <div className="panel" style={{ padding: 8, fontSize: 12, background: '#111' }}>
             Debt Score: {selectedNode.debt?.toFixed(1)}%
          </div>
        </div>
      )}

      {loading && <div style={{ position: 'absolute', top: '50%', left: '50%', color: 'var(--accent-cyan)' }}>GENERATING SPATIAL HIERARCHY...</div>}
    </div>
  )
}
