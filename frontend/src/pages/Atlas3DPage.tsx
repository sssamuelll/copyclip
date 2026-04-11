import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
// @ts-ignore — d3-force-3d has no type declarations
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force-3d'
import { api } from '../api/client'
import type { ArchNode, ArchEdge, CognitiveLoadItem } from '../types/api'

type GraphNode = ArchNode & {
  debt: number
  connectionCount: number
  inbound: string[]
  outbound: string[]
  x?: number
  y?: number
  z?: number
  index?: number
}

type GraphLink = {
  source: number | GraphNode
  target: number | GraphNode
}

const getDebtColor = (debt: number) => {
  if (debt > 70) return 0xff3333
  if (debt > 40) return 0xffaa00
  return 0x00eeff
}

export function Atlas3DPage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [hoveredNodeData, setHoveredNodeData] = useState<GraphNode | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    let scene: THREE.Scene, camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer, controls: OrbitControls
    let raycaster: THREE.Raycaster
    let animationId: number

    const nodesGroup = new THREE.Group()
    const starsGroup = new THREE.Group()
    let edgesMesh: THREE.LineSegments | null = null
    let currentHoveredMesh: THREE.Mesh | null = null
    let currentSelectedMesh: THREE.Mesh | null = null
    let graphNodes: GraphNode[] = []
    let graphEdges: ArchEdge[] = []
    let nodeIndexMap: Map<string, number> = new Map()

    const init = async () => {
      scene = new THREE.Scene()
      scene.background = new THREE.Color(0x000000)
      scene.fog = new THREE.FogExp2(0x000000, 0.0002)

      camera = new THREE.PerspectiveCamera(60, containerRef.current!.clientWidth / containerRef.current!.clientHeight, 1, 10000)
      camera.position.set(0, 400, 1200)

      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
      renderer.setPixelRatio(window.devicePixelRatio)
      renderer.setSize(containerRef.current!.clientWidth, containerRef.current!.clientHeight)
      containerRef.current!.appendChild(renderer.domElement)

      controls = new OrbitControls(camera, renderer.domElement)
      controls.enableDamping = true
      controls.dampingFactor = 0.05

      raycaster = new THREE.Raycaster()

      // Lighting
      const hemiLight = new THREE.HemisphereLight(0xffffff, 0x444444, 1.5)
      scene.add(hemiLight)

      const sun = new THREE.DirectionalLight(0xffffff, 2.0)
      sun.position.set(1000, 1000, 1000)
      scene.add(sun)

      const centerLight = new THREE.PointLight(0x00f0ff, 1, 3000)
      centerLight.position.set(0, 0, 0)
      scene.add(centerLight)

      // Starfield
      const starGeometry = new THREE.BufferGeometry()
      const starPositions: number[] = []
      const starColors: number[] = []
      for (let i = 0; i < 12000; i++) {
        starPositions.push(Math.random() * 8000 - 4000)
        starPositions.push(Math.random() * 8000 - 4000)
        starPositions.push(Math.random() * 8000 - 4000)
        const b = 0.7 + Math.random() * 0.3
        starColors.push(b, b, b)
      }
      starGeometry.setAttribute('position', new THREE.Float32BufferAttribute(starPositions, 3))
      starGeometry.setAttribute('color', new THREE.Float32BufferAttribute(starColors, 3))
      const starMaterial = new THREE.PointsMaterial({ size: 2, vertexColors: true, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending })
      starsGroup.add(new THREE.Points(starGeometry, starMaterial))
      scene.add(starsGroup)

      try {
        const [{ nodes, edges }, cog] = await Promise.all([api.architecture(), api.cognitiveLoad()])
        buildGraph(nodes, edges, cog.items || [])
        setLoading(false)
      } catch (e) {
        console.error(e)
        setLoading(false)
      }

      scene.add(nodesGroup)
      animate()

      window.addEventListener('resize', onWindowResize)
      document.addEventListener('mousemove', onDocumentMouseMove)
      renderer.domElement.addEventListener('click', onMouseClick)
    }

    const buildGraph = (nodes: ArchNode[], edges: ArchEdge[], cogItems: CognitiveLoadItem[]) => {
      graphEdges = edges

      // Build connection counts and neighbor lists
      const inboundMap = new Map<string, string[]>()
      const outboundMap = new Map<string, string[]>()
      for (const e of edges) {
        outboundMap.set(e.from, [...(outboundMap.get(e.from) || []), e.to])
        inboundMap.set(e.to, [...(inboundMap.get(e.to) || []), e.from])
      }

      // Build graph nodes
      graphNodes = nodes.map((node, i) => {
        const inbound = inboundMap.get(node.name) || []
        const outbound = outboundMap.get(node.name) || []
        const cog = cogItems.find(c => c.module === node.name)
        const debt = cog?.cognitive_debt_score || 0
        nodeIndexMap.set(node.name, i)
        return { ...node, debt, connectionCount: inbound.length + outbound.length, inbound, outbound }
      })

      // Build links for d3-force (using indices)
      const links: GraphLink[] = []
      for (const e of edges) {
        const si = nodeIndexMap.get(e.from)
        const ti = nodeIndexMap.get(e.to)
        if (si !== undefined && ti !== undefined) {
          links.push({ source: si, target: ti })
        }
      }

      // Run force simulation to compute positions
      const sim = forceSimulation(graphNodes, 3)
        .force('charge', forceManyBody().strength(-200))
        .force('link', forceLink(links).distance(120))
        .force('center', forceCenter(0, 0, 0))
        .force('collide', forceCollide().radius((d: GraphNode) => getNodeRadius(d.connectionCount, graphNodes.length) + 5))
        .stop()

      // Run simulation to settle
      for (let i = 0; i < 300; i++) sim.tick()

      // Scale positions for 3D space
      const scale = 3
      graphNodes.forEach(n => {
        n.x = (n.x || 0) * scale
        n.y = (n.y || 0) * scale
        n.z = (n.z || 0) * scale
      })

      // Render nodes
      renderNodes(graphNodes)

      // Render edges
      renderEdges(graphNodes, edges)
    }

    const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

    const getNodeRadius = (connectionCount: number, totalNodes: number) => {
      // Graph-aware scale: adapts node sizes to total graph density
      // Ported from CodeGraphContext's getGraphAwareNodeScale()
      const graphScale = clamp(1 + Math.log10(Math.max(totalNodes, 1)) * 0.22, 1, 2)
      const degreeSize = Math.log2(connectionCount + 1) * 4
      return clamp((4 + degreeSize) * graphScale, 5, 35)
    }

    const createLabel = (text: string) => {
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      if (!ctx) return null
      canvas.width = 512
      canvas.height = 128
      ctx.font = '300 36px IBM Plex Mono'
      ctx.fillStyle = '#ffffff'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(text, 256, 64)
      const texture = new THREE.CanvasTexture(canvas)
      const material = new THREE.SpriteMaterial({ map: texture, transparent: true, opacity: 0.7, sizeAttenuation: true })
      const sprite = new THREE.Sprite(material)
      sprite.scale.set(140, 35, 1)
      return sprite
    }

    const renderNodes = (nodes: GraphNode[]) => {
      nodes.forEach((node) => {
        const radius = getNodeRadius(node.connectionCount, nodes.length)
        const nodeContainer = new THREE.Group()
        nodeContainer.position.set(node.x || 0, node.y || 0, node.z || 0)

        const geometry = new THREE.SphereGeometry(radius, 32, 32)
        const color = getDebtColor(node.debt)
        const material = new THREE.MeshStandardMaterial({
          color,
          roughness: 0.4,
          metalness: 0.3,
          emissive: color,
          emissiveIntensity: 0.3,
          transparent: true,
          opacity: 1.0,
        })
        const mesh = new THREE.Mesh(geometry, material)
        mesh.userData = node
        nodeContainer.add(mesh)

        const label = createLabel(node.name.split('/').pop() || node.name)
        if (label) {
          label.position.set(0, -(radius + 15), 0)
          nodeContainer.add(label)
        }

        nodesGroup.add(nodeContainer)
      })
    }

    const renderEdges = (nodes: GraphNode[], edges: ArchEdge[]) => {
      const positions: number[] = []
      for (const e of edges) {
        const si = nodeIndexMap.get(e.from)
        const ti = nodeIndexMap.get(e.to)
        if (si !== undefined && ti !== undefined) {
          const sn = nodes[si]
          const tn = nodes[ti]
          positions.push(sn.x || 0, sn.y || 0, sn.z || 0)
          positions.push(tn.x || 0, tn.y || 0, tn.z || 0)
        }
      }

      const geo = new THREE.BufferGeometry()
      geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))

      const mat = new THREE.LineBasicMaterial({
        color: 0x00eeff,
        transparent: true,
        opacity: 0.15,
        blending: THREE.AdditiveBlending,
      })

      edgesMesh = new THREE.LineSegments(geo, mat)
      scene.add(edgesMesh)
    }

    const highlightEdgesForNode = (nodeName: string) => {
      if (!edgesMesh) return

      // Remove old edges mesh, create two: connected (bright) and unconnected (dim)
      scene.remove(edgesMesh)

      const connectedPos: number[] = []
      const dimPos: number[] = []

      for (const e of graphEdges) {
        const si = nodeIndexMap.get(e.from)
        const ti = nodeIndexMap.get(e.to)
        if (si === undefined || ti === undefined) continue
        const sn = graphNodes[si]
        const tn = graphNodes[ti]
        const coords = [sn.x || 0, sn.y || 0, sn.z || 0, tn.x || 0, tn.y || 0, tn.z || 0]
        if (e.from === nodeName || e.to === nodeName) {
          connectedPos.push(...coords)
        } else {
          dimPos.push(...coords)
        }
      }

      // Dim edges
      if (dimPos.length > 0) {
        const dimGeo = new THREE.BufferGeometry()
        dimGeo.setAttribute('position', new THREE.Float32BufferAttribute(dimPos, 3))
        const dimMat = new THREE.LineBasicMaterial({ color: 0x00eeff, transparent: true, opacity: 0.03, blending: THREE.AdditiveBlending })
        const dimLines = new THREE.LineSegments(dimGeo, dimMat)
        dimLines.userData._edgeType = 'dim'
        scene.add(dimLines)
      }

      // Bright edges
      if (connectedPos.length > 0) {
        const brightGeo = new THREE.BufferGeometry()
        brightGeo.setAttribute('position', new THREE.Float32BufferAttribute(connectedPos, 3))
        const brightMat = new THREE.LineBasicMaterial({ color: 0x00eeff, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending })
        const brightLines = new THREE.LineSegments(brightGeo, brightMat)
        brightLines.userData._edgeType = 'bright'
        scene.add(brightLines)
      }

      edgesMesh = null // Mark as split

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
    }

    const resetEdges = () => {
      // Remove split edge meshes
      const toRemove = scene.children.filter(c => c.userData._edgeType === 'dim' || c.userData._edgeType === 'bright')
      toRemove.forEach(c => {
        scene.remove(c)
        if (c instanceof THREE.LineSegments) {
          c.geometry.dispose()
          ;(c.material as THREE.Material).dispose()
        }
      })

      // Recreate single edges mesh
      if (graphNodes.length > 0) {
        renderEdges(graphNodes, graphEdges)
      }

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
    }

    const highlightNode = (node: THREE.Mesh, intensity: number) => {
      const mat = node.material as THREE.MeshStandardMaterial
      mat.emissiveIntensity = intensity
      const label = node.parent?.children.find(c => c.type === 'Sprite') as THREE.Sprite
      if (label) {
        ;(label.material as THREE.SpriteMaterial).opacity = 1.0
        label.scale.set(180, 45, 1)
      }
    }

    const resetNodeVisual = (node: THREE.Mesh) => {
      const mat = node.material as THREE.MeshStandardMaterial
      mat.emissiveIntensity = 0.3
      mat.opacity = 1.0
      const label = node.parent?.children.find(c => c.type === 'Sprite') as THREE.Sprite
      if (label) {
        ;(label.material as THREE.SpriteMaterial).opacity = 0.7
        label.scale.set(140, 35, 1)
      }
    }

    const onDocumentMouseMove = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect()
      const mx = ((event.clientX - rect.left) / rect.width) * 2 - 1
      const my = -((event.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera({ x: mx, y: my } as any, camera)
      const intersects = raycaster.intersectObjects(nodesGroup.children, true)
      const sphere = intersects.find(i => i.object.type === 'Mesh')

      if (sphere) {
        const obj = sphere.object as THREE.Mesh
        if (currentHoveredMesh !== obj) {
          if (currentHoveredMesh && currentHoveredMesh !== currentSelectedMesh) {
            resetNodeVisual(currentHoveredMesh)
          }
          if (!currentSelectedMesh) resetEdges()
          currentHoveredMesh = obj
          highlightNode(obj, 0.8)
          if (!currentSelectedMesh) {
            highlightEdgesForNode((obj.userData as GraphNode).name)
          }
          setHoveredNodeData(obj.userData as GraphNode)
        }
        renderer.domElement.style.cursor = 'pointer'
      } else {
        if (currentHoveredMesh && currentHoveredMesh !== currentSelectedMesh) {
          resetNodeVisual(currentHoveredMesh)
        }
        currentHoveredMesh = null
        if (!currentSelectedMesh) resetEdges()
        setHoveredNodeData(null)
        renderer.domElement.style.cursor = 'default'
      }
    }

    const onMouseClick = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect()
      const mx = ((event.clientX - rect.left) / rect.width) * 2 - 1
      const my = -((event.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera({ x: mx, y: my } as any, camera)
      const intersects = raycaster.intersectObjects(nodesGroup.children, true)
      const sphere = intersects.find(i => i.object.type === 'Mesh')

      if (sphere) {
        const obj = sphere.object as THREE.Mesh
        if (currentSelectedMesh) resetNodeVisual(currentSelectedMesh)
        resetEdges()
        currentSelectedMesh = obj
        highlightNode(obj, 1.5)
        highlightEdgesForNode((obj.userData as GraphNode).name)
        setSelectedNode(obj.userData as GraphNode)
      } else {
        if (currentSelectedMesh) resetNodeVisual(currentSelectedMesh)
        currentSelectedMesh = null
        resetEdges()
        setSelectedNode(null)
      }
    }

    const onWindowResize = () => {
      if (!containerRef.current) return
      camera.aspect = containerRef.current.clientWidth / containerRef.current.clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight)
    }

    const animate = () => {
      animationId = requestAnimationFrame(animate)
      controls.update()
      starsGroup.rotation.y += 0.0001

      // Lerp node scale on hover/select
      nodesGroup.children.forEach(container => {
        const mesh = container.children.find(c => c.type === 'Mesh') as THREE.Mesh
        if (!mesh) return
        const isHovered = currentHoveredMesh === mesh
        const isSelected = currentSelectedMesh === mesh
        const targetScale = isSelected ? 2.0 : isHovered ? 1.5 : 1.0
        mesh.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.1)
      })

      // Distance-based label opacity fade (skip when focus/dim is active)
      if (!currentHoveredMesh && !currentSelectedMesh) {
        nodesGroup.children.forEach(container => {
          const label = container.children.find(c => c.type === 'Sprite') as THREE.Sprite
          if (!label) return
          const dist = camera.position.distanceTo(container.position)
          const maxFade = 2500
          const opacity = Math.max(0.1, Math.min(0.9, 1.0 - dist / maxFade))
          ;(label.material as THREE.SpriteMaterial).opacity = opacity
        })
      }

      renderer.render(scene, camera)
    }

    init()
    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', onWindowResize)
      document.removeEventListener('mousemove', onDocumentMouseMove)
      if (renderer) renderer.dispose()
      if (containerRef.current) {
        while (containerRef.current.firstChild) {
          containerRef.current.removeChild(containerRef.current.firstChild)
        }
      }
    }
  }, [])

  const activeNode = selectedNode || hoveredNodeData

  return (
    <div style={{ position: 'relative', width: '100%', height: 'calc(100vh - 100px)', background: '#000', borderRadius: 12, overflow: 'hidden' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

      <div style={{ position: 'absolute', top: 30, left: 30, pointerEvents: 'none' }}>
        <div style={{ fontSize: 10, color: '#666', letterSpacing: 3, textTransform: 'uppercase', marginBottom: 4 }}>// cosmic_project_atlas</div>
        <div style={{ fontSize: 24, color: '#fff', fontWeight: 300 }}>The Atlas</div>
      </div>

      {activeNode && (
        <div
          data-augmented-ui=""
          className={`atlas-info-panel${selectedNode ? ' atlas-info-panel--locked' : ''}`}
        >
          <div style={{ fontSize: 9, color: selectedNode ? '#00eeff' : '#666', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            {selectedNode ? 'Persistent link established' : 'Reading project body\u2026'}
          </div>
          <div style={{ fontSize: 18, color: '#fff', marginBottom: 16, fontWeight: 500 }}>{activeNode.name}</div>
          <div style={{ display: 'grid', gap: 12 }}>
            <div className="panel" style={{ padding: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid #222' }}>
              <div style={{ fontSize: 10, color: '#666', marginBottom: 4 }}>COGNITIVE_DEBT</div>
              <div style={{ fontSize: 16, color: activeNode.debt > 50 ? '#ff4444' : '#00ffaa' }}>{activeNode.debt?.toFixed(1)}%</div>
            </div>
            <div className="panel" style={{ padding: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid #222' }}>
              <div style={{ fontSize: 10, color: '#666', marginBottom: 6 }}>CONNECTIONS</div>
              <div style={{ display: 'flex', gap: 16 }}>
                <div><span style={{ color: '#00eeff', fontSize: 14 }}>{activeNode.inbound.length}</span> <span style={{ fontSize: 10, color: '#666' }}>inbound</span></div>
                <div><span style={{ color: '#00eeff', fontSize: 14 }}>{activeNode.outbound.length}</span> <span style={{ fontSize: 10, color: '#666' }}>outbound</span></div>
              </div>
            </div>
            {activeNode.outbound.length > 0 && (
              <div>
                <div style={{ fontSize: 10, color: '#666', marginBottom: 6 }}>IMPORTS (outbound)</div>
                <div style={{ fontSize: 11, color: '#888', lineHeight: 1.8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {activeNode.outbound.map((name: string, i: number) => (
                    <span key={name}>
                      <span style={{ color: '#00eeff' }}>{name.split('/').pop()}</span>
                      {i < activeNode.outbound.length - 1 && <span style={{ color: '#333', margin: '0 2px' }}>|</span>}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {activeNode.inbound.length > 0 && (
              <div>
                <div style={{ fontSize: 10, color: '#666', marginBottom: 6 }}>DEPENDENTS (inbound)</div>
                <div style={{ fontSize: 11, color: '#888', lineHeight: 1.8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {activeNode.inbound.map((name: string, i: number) => (
                    <span key={name}>
                      <span style={{ color: '#00eeff' }}>{name.split('/').pop()}</span>
                      {i < activeNode.inbound.length - 1 && <span style={{ color: '#333', margin: '0 2px' }}>|</span>}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {selectedNode && (
              <div style={{ fontSize: 11, color: '#00eeff', opacity: 0.6 }}>
                Click in deep space to release focus.
              </div>
            )}
          </div>
        </div>
      )}

      {loading && <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#fff', letterSpacing: 4, fontWeight: 200 }}>MATERIALIZING THE ATLAS{'\u2026'}</div>}
    </div>
  )
}
