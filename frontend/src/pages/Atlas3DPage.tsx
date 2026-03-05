import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { api } from '../api/client'
import type { ArchNode, CognitiveLoadItem } from '../types/api'

export function Atlas3DPage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState<any>(null)
  const [hoveredNodeData, setHoveredNodeData] = useState<any>(null)

  useEffect(() => {
    if (!containerRef.current) return

    let scene: THREE.Scene, camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer, controls: OrbitControls
    let raycaster: THREE.Raycaster, mouse: THREE.Vector2
    let animationId: number
    
    const nodesGroup = new THREE.Group()
    const starsGroup = new THREE.Group()
    let currentHoveredMesh: THREE.Mesh | null = null
    let currentSelectedMesh: THREE.Mesh | null = null

    const init = async () => {
      scene = new THREE.Scene()
      scene.background = new THREE.Color(0x000000)
      scene.fog = new THREE.FogExp2(0x000000, 0.0002)

      camera = new THREE.PerspectiveCamera(60, containerRef.current!.clientWidth / containerRef.current!.clientHeight, 1, 10000)
      camera.position.set(0, 600, 1800)

      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
      renderer.setPixelRatio(window.devicePixelRatio)
      renderer.setSize(containerRef.current!.clientWidth, containerRef.current!.clientHeight)
      containerRef.current!.appendChild(renderer.domElement)

      controls = new OrbitControls(camera, renderer.domElement)
      controls.enableDamping = true
      controls.dampingFactor = 0.05

      raycaster = new THREE.Raycaster()
      mouse = new THREE.Vector2()

      // --- BRIGHT GALAXY LIGHTING ---
      // 1. Hemisphere Light (Top-down ambient light)
      const hemiLight = new THREE.HemisphereLight(0xffffff, 0x444444, 1.5)
      scene.add(hemiLight)

      // 2. Powerful Directional Light (The "Star" of the system)
      const sun = new THREE.DirectionalLight(0xffffff, 2.0)
      sun.position.set(1000, 1000, 1000)
      scene.add(sun)

      // 3. Central Ambient Glow
      const centerLight = new THREE.PointLight(0x00f0ff, 1, 3000)
      centerLight.position.set(0, 0, 0)
      scene.add(centerLight)

      // Stars
      const starGeometry = new THREE.BufferGeometry()
      const starPositions = []
      const starColors = []
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
        const [{ nodes }, cog] = await Promise.all([api.architecture(), api.cognitiveLoad()])
        renderPlanets(nodes, cog.items || [])
        setLoading(false)
      } catch (e) {
        console.error(e)
      }

      scene.add(nodesGroup)
      animate()

      window.addEventListener('resize', onWindowResize)
      document.addEventListener('mousemove', onDocumentMouseMove)
      renderer.domElement.addEventListener('click', onMouseClick)
    }

    const createPlanetLabel = (text: string) => {
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

    const renderPlanets = (nodes: ArchNode[], cogItems: CognitiveLoadItem[]) => {
      nodes.forEach((node, i) => {
        const t = i / nodes.length
        const angle = 22 * t
        const radius = 900 * Math.sqrt(t)
        const x = Math.cos(angle) * radius
        const y = (Math.random() - 0.5) * 500
        const z = Math.sin(angle) * radius

        const cog = cogItems.find(c => c.module === node.name)
        const debt = cog?.cognitive_debt_score || 0
        const baseSize = 10 + (debt / 5)
        
        const nodeContainer = new THREE.Group()
        nodeContainer.position.set(x, y, z)

        const geometry = new THREE.SphereGeometry(baseSize, 32, 32)
        const material = new THREE.MeshStandardMaterial({ 
          color: getDebtColor(debt), 
          roughness: 0.4, // Shinier
          metalness: 0.3,
          emissive: getDebtColor(debt),
          emissiveIntensity: 0.3 // Brighter base
        })
        const planet = new THREE.Mesh(geometry, material)
        planet.userData = { ...node, debt, baseSize }
        nodeContainer.add(planet)

        const label = createPlanetLabel(node.name.split('/').pop() || node.name)
        if (label) {
          label.position.set(0, -(baseSize + 35), 0)
          nodeContainer.add(label)
        }

        nodesGroup.add(nodeContainer)
      })
    }

    const getDebtColor = (debt: number) => {
      if (debt > 70) return 0xff3333
      if (debt > 40) return 0xffaa00
      return 0x00eeff
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
          if (currentHoveredMesh && currentHoveredMesh !== currentSelectedMesh) resetPlanet(currentHoveredMesh)
          currentHoveredMesh = obj
          highlightPlanet(obj, 0.8)
          setHoveredNodeData(obj.userData)
        }
        renderer.domElement.style.cursor = 'pointer'
      } else {
        if (currentHoveredMesh && currentHoveredMesh !== currentSelectedMesh) resetPlanet(currentHoveredMesh)
        currentHoveredMesh = null
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
        if (currentSelectedMesh) resetPlanet(currentSelectedMesh)
        currentSelectedMesh = obj
        highlightPlanet(obj, 1.5)
        setSelectedNode(obj.userData)
      } else {
        if (currentSelectedMesh) resetPlanet(currentSelectedMesh)
        currentSelectedMesh = null
        setSelectedNode(null)
      }
    }

    const highlightPlanet = (node: THREE.Mesh, intensity: number) => {
      const mat = node.material as THREE.MeshStandardMaterial
      mat.emissiveIntensity = intensity
      const label = node.parent?.children.find(c => c.type === 'Sprite') as THREE.Sprite
      if (label) {
        (label.material as THREE.SpriteMaterial).opacity = 1.0
        label.scale.set(180, 45, 1)
      }
    }

    const resetPlanet = (node: THREE.Mesh) => {
      const mat = node.material as THREE.MeshStandardMaterial
      mat.emissiveIntensity = 0.3
      const label = node.parent?.children.find(c => c.type === 'Sprite') as THREE.Sprite
      if (label) {
        (label.material as THREE.SpriteMaterial).opacity = 0.7
        label.scale.set(140, 35, 1)
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
      nodesGroup.rotation.y += 0.0002

      nodesGroup.children.forEach(container => {
        const planet = container.children.find(c => c.type === 'Mesh') as THREE.Mesh
        const isHovered = currentHoveredMesh === planet
        const isSelected = currentSelectedMesh === planet
        const targetScale = (isHovered || isSelected) ? 2.8 : 1.0
        planet.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.1)
      })

      renderer.render(scene, camera)
    }

    init()
    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', onWindowResize)
      document.removeEventListener('mousemove', onDocumentMouseMove)
      if (renderer) renderer.dispose()
      if (containerRef.current) containerRef.current.innerHTML = ''
    }
  }, [])

  // The displayed info comes from selectedNode IF set, otherwise from hoveredNodeData
  const activeNode = selectedNode || hoveredNodeData

  return (
    <div style={{ position: 'relative', width: '100%', height: 'calc(100vh - 100px)', background: '#000', borderRadius: 12, overflow: 'hidden' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      
      <div style={{ position: 'absolute', top: 30, left: 30, pointerEvents: 'none' }}>
        <div style={{ fontSize: 10, color: '#666', letterSpacing: 3, textTransform: 'uppercase', marginBottom: 4 }}>// autonomous_project_universe</div>
        <div style={{ fontSize: 24, color: '#fff', fontWeight: 300 }}>Deep Space Atlas</div>
      </div>
      
      {activeNode && (
        <div style={{ 
          position: 'absolute', top: 30, right: 30, width: 320, 
          background: 'rgba(0,0,0,0.85)', border: `1px solid ${selectedNode ? '#00eeff' : '#333'}`, 
          borderRadius: 8, padding: 24, backdropFilter: 'blur(16px)',
          boxShadow: selectedNode ? '0 0 40px rgba(0,238,255,0.15)' : '0 8px 32px rgba(0,0,0,0.5)',
          transition: 'all 0.2s ease'
        }}>
          <div style={{ fontSize: 9, color: selectedNode ? '#00eeff' : '#666', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>
            {selectedNode ? 'Persistent Link Established' : 'Scanning Celestial Body...'}
          </div>
          <div style={{ fontSize: 18, color: '#fff', marginBottom: 16, fontWeight: 500 }}>{activeNode.name}</div>
          <div style={{ display: 'grid', gap: 12 }}>
             <div className="panel" style={{ padding: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid #222' }}>
                <div style={{ fontSize: 10, color: '#666', marginBottom: 4 }}>COGNITIVE_DEBT</div>
                <div style={{ fontSize: 16, color: activeNode.debt > 50 ? '#ff4444' : '#00ffaa' }}>{activeNode.debt?.toFixed(1)}%</div>
             </div>
             {selectedNode && (
               <div style={{ fontSize: 11, color: '#00eeff', opacity: 0.8 }}>
                 Click in deep space to release focus.
               </div>
             )}
          </div>
        </div>
      )}

      {loading && <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#fff', letterSpacing: 4, fontWeight: 200 }}>IGNITING STARCORES...</div>}
    </div>
  )
}
