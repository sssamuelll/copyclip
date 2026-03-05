import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { api } from '../api/client'
import type { ArchNode, CognitiveLoadItem } from '../types/api'

export function Atlas3DPage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [selectedNode, setSelectedNode] = useState<any>(null)

  useEffect(() => {
    if (!containerRef.current) return

    let scene: THREE.Scene, camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer
    let raycaster: THREE.Raycaster, mouse: THREE.Vector2
    let mouseX = 0, mouseY = 0
    let windowHalfX = window.innerWidth / 2
    let windowHalfY = window.innerHeight / 2
    let animationId: number
    
    const nodesGroup = new THREE.Group()
    const starsGroup = new THREE.Group()
    let hoveredObject: THREE.Mesh | null = null

    const init = async () => {
      // 1. Scene & Camera Setup
      scene = new THREE.Scene()
      scene.background = new THREE.Color(0x000000)
      // Bloom effect simulation with light and fog
      scene.fog = new THREE.FogExp2(0x000000, 0.0005)

      camera = new THREE.PerspectiveCamera(60, containerRef.current!.clientWidth / containerRef.current!.clientHeight, 1, 4000)
      camera.position.z = 900

      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
      renderer.setPixelRatio(window.devicePixelRatio)
      renderer.setSize(containerRef.current!.clientWidth, containerRef.current!.clientHeight)
      containerRef.current!.appendChild(renderer.domElement)

      raycaster = new THREE.Raycaster()
      mouse = new THREE.Vector2()

      // 2. Bright Stars (The Vivid Universe)
      const starGeometry = new THREE.BufferGeometry()
      const starPositions = []
      const starColors = []
      for (let i = 0; i < 8000; i++) {
        starPositions.push(Math.random() * 3000 - 1500)
        starPositions.push(Math.random() * 3000 - 1500)
        starPositions.push(Math.random() * 3000 - 1500)
        // Variety in star brightness
        const brightness = 0.5 + Math.random() * 0.5
        starColors.push(brightness, brightness, brightness)
      }
      starGeometry.setAttribute('position', new THREE.Float32BufferAttribute(starPositions, 3))
      starGeometry.setAttribute('color', new THREE.Float32BufferAttribute(starColors, 3))
      
      const starMaterial = new THREE.PointsMaterial({ 
        size: 2, 
        vertexColors: true,
        transparent: true, 
        opacity: 0.9,
        blending: THREE.AdditiveBlending 
      })
      const stars = new THREE.Points(starGeometry, starMaterial)
      starsGroup.add(stars)
      scene.add(starsGroup)

      // 3. Project Nodes (The Luminous Constellation)
      try {
        const [{ nodes }, cog] = await Promise.all([
          api.architecture(),
          api.cognitiveLoad()
        ])
        renderNodes(nodes, cog.items || [])
        setLoading(false)
      } catch (e) {
        console.error(e)
      }

      scene.add(nodesGroup)
      
      // Additional ambient glow
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.2)
      scene.add(ambientLight)

      animate()

      window.addEventListener('resize', onWindowResize)
      document.addEventListener('mousemove', onDocumentMouseMove)
      renderer.domElement.addEventListener('click', onMouseClick)
    }

    const renderNodes = (nodes: ArchNode[], cogItems: CognitiveLoadItem[]) => {
      nodes.forEach((node, i) => {
        const t = i / nodes.length
        const angle = 25 * t
        const radius = 500 * Math.sqrt(t)
        
        const x = Math.cos(angle) * radius
        const y = (Math.random() - 0.5) * 150
        const z = Math.sin(angle) * radius

        const cog = cogItems.find(c => c.module === node.name)
        const debt = cog?.cognitive_debt_score || 0
        
        const baseSize = 4 + (debt / 12)
        const geometry = new THREE.SphereGeometry(baseSize, 32, 32)
        
        // High visibility material
        const material = new THREE.MeshBasicMaterial({ 
          color: getDebtColor(debt),
          transparent: true, 
          opacity: 0.9
        })
        
        const sphere = new THREE.Mesh(geometry, material)
        sphere.position.set(x, y, z)
        // Store metadata and original scale for animation
        sphere.userData = { ...node, debt, originalScale: 1, baseSize }
        nodesGroup.add(sphere)
      })
    }

    const getDebtColor = (debt: number) => {
      if (debt > 70) return 0xff2222 // Vivid Red
      if (debt > 40) return 0xffcc00 // Bright Amber
      return 0x00ffff // Neon Cyan
    }

    const onDocumentMouseMove = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect()
      mouseX = event.clientX - windowHalfX
      mouseY = event.clientY - windowHalfY

      const mx = ((event.clientX - rect.left) / rect.width) * 2 - 1
      const my = -((event.clientY - rect.top) / rect.height) * 2 + 1
      
      raycaster.setFromCamera({ x: mx, y: my } as any, camera)
      const intersects = raycaster.intersectObjects(nodesGroup.children)
      
      if (intersects.length > 0) {
        const obj = intersects[0].object as THREE.Mesh
        if (hoveredObject !== obj) {
          if (hoveredObject) resetNode(hoveredObject)
          hoveredObject = obj
          highlightNode(obj)
        }
        renderer.domElement.style.cursor = 'pointer'
      } else {
        if (hoveredObject) resetNode(hoveredObject)
        hoveredObject = null
        renderer.domElement.style.cursor = 'default'
      }
    }

    const highlightNode = (node: THREE.Mesh) => {
      // Scale up and increase brightness
      node.scale.set(2.5, 2.5, 2.5) // "Suddendly get closer" effect
      const mat = node.material as THREE.MeshBasicMaterial
      mat.opacity = 1.0
      // Add a point light to selected node temporarily could be expensive, 
      // instead we rely on color/scale for now.
    }

    const resetNode = (node: THREE.Mesh) => {
      node.scale.set(1, 1, 1)
      const mat = node.material as THREE.MeshBasicMaterial
      mat.opacity = 0.9
    }

    const onMouseClick = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect()
      const mx = ((event.clientX - rect.left) / rect.width) * 2 - 1
      const my = -((event.clientY - rect.top) / rect.height) * 2 + 1
      raycaster.setFromCamera({ x: mx, y: my } as any, camera)
      const intersects = raycaster.intersectObjects(nodesGroup.children)
      if (intersects.length > 0) {
        setSelectedNode(intersects[0].object.userData)
      } else {
        setSelectedNode(null)
      }
    }

    const onWindowResize = () => {
      if (!containerRef.current) return
      windowHalfX = window.innerWidth / 2
      windowHalfY = window.innerHeight / 2
      camera.aspect = containerRef.current.clientWidth / containerRef.current.clientHeight
      camera.updateProjectionMatrix()
      renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight)
    }

    const animate = () => {
      animationId = requestAnimationFrame(animate)
      
      // Parallax
      camera.position.x += (mouseX - camera.position.x) * 0.03
      camera.position.y += (-mouseY - camera.position.y) * 0.03
      camera.lookAt(scene.position)

      // Rotations
      starsGroup.rotation.y += 0.0003
      nodesGroup.rotation.y += 0.0006

      // Interpolate scale for smooth hover
      nodesGroup.children.forEach(child => {
        const targetScale = hoveredObject === child ? 2.2 : 1.0
        child.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.1)
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

  return (
    <div style={{ position: 'relative', width: '100%', height: 'calc(100vh - 100px)', background: '#000', borderRadius: 12, overflow: 'hidden' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      
      <div style={{ position: 'absolute', top: 30, left: 30, pointerEvents: 'none' }}>
        <div style={{ fontSize: 10, color: '#555', letterSpacing: 3, textTransform: 'uppercase', marginBottom: 4 }}>// vivid_cosmic_atlas_v3</div>
        <div style={{ fontSize: 24, color: '#fff', fontWeight: 300, letterSpacing: -0.5 }}>The Project Universe</div>
      </div>

      {selectedNode && (
        <div style={{ 
          position: 'absolute', top: 30, right: 30, width: 280, 
          background: 'rgba(0,0,0,0.85)', border: '1px solid #333', 
          borderRadius: 8, padding: 24, backdropFilter: 'blur(12px)',
          boxShadow: '0 0 20px rgba(0,238,255,0.1)'
        }}>
          <div style={{ fontSize: 10, color: '#888', marginBottom: 8 }}>// celestial_body_focused</div>
          <div style={{ fontSize: 18, color: '#00ffff', marginBottom: 16, fontWeight: 500 }}>{selectedNode.name}</div>
          <div className="panel" style={{ padding: 12, background: 'rgba(255,255,255,0.03)', fontSize: 13, border: '1px solid #222' }}>
            Cognitive Debt: <span style={{ color: selectedNode.debt > 50 ? '#ff4444' : '#00ffaa', fontWeight: 'bold' }}>{selectedNode.debt?.toFixed(1)}%</span>
          </div>
        </div>
      )}

      {loading && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#00ffff', letterSpacing: 2, fontWeight: 'bold' }}>
          IGNITING THE UNIVERSE...
        </div>
      )}
    </div>
  )
}
