import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { api } from '../api/client'
import type { ArchNode, ArchEdge, CognitiveLoadItem } from '../types/api'

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

    const init = async () => {
      // 1. Scene & Camera Setup
      scene = new THREE.Scene()
      scene.background = new THREE.Color(0x000000)
      scene.fog = new THREE.FogExp2(0x000000, 0.0008)

      camera = new THREE.PerspectiveCamera(60, containerRef.current!.clientWidth / containerRef.current!.clientHeight, 1, 3000)
      camera.position.z = 800

      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
      renderer.setPixelRatio(window.devicePixelRatio)
      renderer.setSize(containerRef.current!.clientWidth, containerRef.current!.clientHeight)
      containerRef.current!.appendChild(renderer.domElement)

      raycaster = new THREE.Raycaster()
      mouse = new THREE.Vector2()

      // 2. Stars Background (The Universe)
      const starGeometry = new THREE.BufferGeometry()
      const starPositions = []
      for (let i = 0; i < 5000; i++) {
        starPositions.push(Math.random() * 2000 - 1000)
        starPositions.push(Math.random() * 2000 - 1000)
        starPositions.push(Math.random() * 2000 - 1000)
      }
      starGeometry.setAttribute('position', new THREE.Float32BufferAttribute(starPositions, 3))
      const starMaterial = new THREE.PointsMaterial({ color: 0x888888, size: 1, transparent: true, opacity: 0.5 })
      const stars = new THREE.Points(starGeometry, starMaterial)
      starsGroup.add(stars)
      scene.add(starsGroup)

      // 3. Project Nodes (The Constellation)
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
      animate()

      // Event Listeners
      window.addEventListener('resize', onWindowResize)
      document.addEventListener('mousemove', onDocumentMouseMove)
      renderer.domElement.addEventListener('click', onMouseClick)
    }

    const renderNodes = (nodes: ArchNode[], cogItems: CognitiveLoadItem[]) => {
      nodes.forEach((node, i) => {
        // Spiral / Galactic distribution
        const t = i / nodes.length
        const angle = 20 * t
        const radius = 400 * Math.sqrt(t)
        
        const x = Math.cos(angle) * radius
        const y = (Math.random() - 0.5) * 100
        const z = Math.sin(angle) * radius

        const cog = cogItems.find(c => c.module === node.name)
        const debt = cog?.cognitive_debt_score || 0
        
        const size = 3 + (debt / 15)
        const geometry = new THREE.SphereGeometry(size, 16, 16)
        const material = new THREE.MeshBasicMaterial({ 
          color: getDebtColor(debt),
          transparent: true, 
          opacity: 0.8
        })
        
        const sphere = new THREE.Mesh(geometry, material)
        sphere.position.set(x, y, z)
        sphere.userData = { ...node, debt }
        nodesGroup.add(sphere)
      })
    }

    const getDebtColor = (debt: number) => {
      if (debt > 70) return 0xff4444 // Red
      if (debt > 40) return 0xffaa00 // Orange
      return 0x00eeff // Cyan
    }

    const onDocumentMouseMove = (event: MouseEvent) => {
      mouseX = event.clientX - windowHalfX
      mouseY = event.clientY - windowHalfY

      // Hover Detection for Cursor Change
      const rect = renderer.domElement.getBoundingClientRect()
      const mx = ((event.clientX - rect.left) / rect.width) * 2 - 1
      const my = -((event.clientY - rect.top) / rect.height) * 2 + 1
      
      raycaster.setFromCamera({ x: mx, y: my } as any, camera)
      const intersects = raycaster.intersectObjects(nodesGroup.children)
      renderer.domElement.style.cursor = intersects.length > 0 ? 'pointer' : 'default'
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
      
      // Smooth Camera Parallax (From earth perspective)
      camera.position.x += (mouseX - camera.position.x) * 0.02
      camera.position.y += (-mouseY - camera.position.y) * 0.02
      camera.lookAt(scene.position)

      // Gentle rotation of the universe
      starsGroup.rotation.y += 0.0002
      nodesGroup.rotation.y += 0.0005

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
      
      {/* Overlay UI */}
      <div style={{ position: 'absolute', top: 30, left: 30, pointerEvents: 'none' }}>
        <div style={{ fontSize: 10, color: '#444', letterSpacing: 3, textTransform: 'uppercase', marginBottom: 4 }}>// cosmic_intent_atlas</div>
        <div style={{ fontSize: 24, color: '#fff', fontWeight: 300, letterSpacing: -0.5 }}>The Project Universe</div>
      </div>

      {selectedNode && (
        <div style={{ 
          position: 'absolute', top: 30, right: 30, width: 280, 
          background: 'rgba(0,0,0,0.8)', border: '1px solid #222', 
          borderRadius: 8, padding: 24, backdropFilter: 'blur(10px)' 
        }}>
          <div style={{ fontSize: 10, color: '#666', marginBottom: 8 }}>// celestial_body_focused</div>
          <div style={{ fontSize: 18, color: '#00eeff', marginBottom: 16 }}>{selectedNode.name}</div>
          <div className="panel" style={{ padding: 12, background: 'rgba(255,255,255,0.02)', fontSize: 13 }}>
            Cognitive Debt: <span style={{ color: selectedNode.debt > 50 ? '#ff4444' : '#00ffaa' }}>{selectedNode.debt?.toFixed(1)}%</span>
          </div>
        </div>
      )}

      {loading && (
        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#333', letterSpacing: 2 }}>
          CALIBRATING TELESCOPE...
        </div>
      )}
    </div>
  )
}
