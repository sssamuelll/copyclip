import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { api } from '../api/client'
import type { ArchNode, CognitiveLoadItem } from '../types/api'

export function Atlas3DPage() {
  const containerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [focusedNode, setFocusedNode] = useState<any>(null)

  useEffect(() => {
    if (!containerRef.current) return

    let scene: THREE.Scene, camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer, controls: OrbitControls
    let raycaster: THREE.Raycaster, mouse: THREE.Vector2
    let animationId: number
    
    const nodesGroup = new THREE.Group()
    const starsGroup = new THREE.Group()
    let hoveredObject: THREE.Mesh | null = null

    const init = async () => {
      scene = new THREE.Scene()
      scene.background = new THREE.Color(0x000000)
      scene.fog = new THREE.FogExp2(0x000000, 0.0004)

      camera = new THREE.PerspectiveCamera(60, containerRef.current!.clientWidth / containerRef.current!.clientHeight, 1, 6000)
      camera.position.set(0, 400, 1200)

      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
      renderer.setPixelRatio(window.devicePixelRatio)
      renderer.setSize(containerRef.current!.clientWidth, containerRef.current!.clientHeight)
      containerRef.current!.appendChild(renderer.domElement)

      // OrbitControls for Free Navigation (Zoom / Two fingers)
      controls = new OrbitControls(camera, renderer.domElement)
      controls.enableDamping = true
      controls.dampingFactor = 0.05
      controls.rotateSpeed = 0.5
      controls.minDistance = 100
      controls.maxDistance = 3000

      raycaster = new THREE.Raycaster()
      mouse = new THREE.Vector2()

      // Bright Universe
      const starGeometry = new THREE.BufferGeometry()
      const starPositions = []
      const starColors = []
      for (let i = 0; i < 9000; i++) {
        starPositions.push(Math.random() * 5000 - 2500)
        starPositions.push(Math.random() * 5000 - 2500)
        starPositions.push(Math.random() * 5000 - 2500)
        const b = 0.5 + Math.random() * 0.5
        starColors.push(b, b, b)
      }
      starGeometry.setAttribute('position', new THREE.Float32BufferAttribute(starPositions, 3))
      starGeometry.setAttribute('color', new THREE.Float32BufferAttribute(starColors, 3))
      const starMaterial = new THREE.PointsMaterial({ size: 2, vertexColors: true, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending })
      starsGroup.add(new THREE.Points(starGeometry, starMaterial))
      scene.add(starsGroup)

      try {
        const [{ nodes }, cog] = await Promise.all([api.architecture(), api.cognitiveLoad()])
        renderNodes(nodes, cog.items || [])
        setLoading(false)
      } catch (e) {
        console.error(e)
      }

      scene.add(nodesGroup)
      scene.add(new THREE.AmbientLight(0xffffff, 0.4))
      animate()

      window.addEventListener('resize', onWindowResize)
      document.addEventListener('mousemove', onDocumentMouseMove)
    }

    const createTextLabel = (text: string) => {
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      if (!ctx) return null
      
      canvas.width = 512
      canvas.height = 128
      
      // Transparent background (just text)
      ctx.font = 'bold 36px IBM Plex Mono'
      ctx.fillStyle = '#ffffff'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      
      // Glow effect on text
      ctx.shadowColor = '#00ffff'
      ctx.shadowBlur = 8
      ctx.fillText(text, 256, 64)
      
      const texture = new THREE.CanvasTexture(canvas)
      const material = new THREE.SpriteMaterial({ 
        map: texture, 
        transparent: true, 
        opacity: 0.7,
        sizeAttenuation: true 
      })
      const sprite = new THREE.Sprite(material)
      sprite.scale.set(140, 35, 1)
      return sprite
    }

    const renderNodes = (nodes: ArchNode[], cogItems: CognitiveLoadItem[]) => {
      nodes.forEach((node, i) => {
        const t = i / nodes.length
        const angle = 22 * t
        const radius = 700 * Math.sqrt(t)
        const x = Math.cos(angle) * radius
        const y = (Math.random() - 0.5) * 300
        const z = Math.sin(angle) * radius

        const cog = cogItems.find(c => c.module === node.name)
        const debt = cog?.cognitive_debt_score || 0
        const baseSize = 6 + (debt / 8)
        
        const nodeContainer = new THREE.Group()
        nodeContainer.position.set(x, y, z)

        const geometry = new THREE.SphereGeometry(baseSize, 32, 32)
        const material = new THREE.MeshBasicMaterial({ 
          color: getDebtColor(debt), 
          transparent: true, 
          opacity: 0.9
        })
        const sphere = new THREE.Mesh(geometry, material)
        sphere.userData = { ...node, debt, baseSize }
        nodeContainer.add(sphere)

        const label = createTextLabel(node.name.split('/').pop() || node.name)
        if (label) {
          label.position.set(0, -(baseSize + 30), 0)
          nodeContainer.add(label)
        }

        nodesGroup.add(nodeContainer)
      })
    }

    const getDebtColor = (debt: number) => {
      if (debt > 70) return 0xff3333
      if (debt > 40) return 0xffcc00
      return 0x00ffff
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
        if (hoveredObject !== obj) {
          if (hoveredObject) resetNode(hoveredObject)
          hoveredObject = obj
          highlightNode(obj)
          setFocusedNode(obj.userData) // Automatically show info on hover
        }
        renderer.domElement.style.cursor = 'pointer'
      } else {
        if (hoveredObject) {
          resetNode(hoveredObject)
          hoveredObject = null
          setFocusedNode(null)
        }
        renderer.domElement.style.cursor = 'default'
      }
    }

    const highlightNode = (node: THREE.Mesh) => {
      const mat = node.material as THREE.MeshBasicMaterial
      mat.opacity = 1.0
      const label = node.parent?.children.find(c => c.type === 'Sprite') as THREE.Sprite
      if (label) {
        (label.material as THREE.SpriteMaterial).opacity = 1.0
        label.scale.set(200, 50, 1)
      }
    }

    const resetNode = (node: THREE.Mesh) => {
      const mat = node.material as THREE.MeshBasicMaterial
      mat.opacity = 0.9
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
      nodesGroup.rotation.y += 0.0003

      nodesGroup.children.forEach(container => {
        const sphere = container.children.find(c => c.type === 'Mesh') as THREE.Mesh
        const targetScale = hoveredObject === sphere ? 2.8 : 1.0
        sphere.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.1)
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
        <div style={{ fontSize: 10, color: '#444', letterSpacing: 3, textTransform: 'uppercase', marginBottom: 4 }}>// deep_space_atlas_v3</div>
        <div style={{ fontSize: 24, color: '#fff', fontWeight: 300 }}>Autonomous Project Universe</div>
      </div>
      
      {focusedNode && (
        <div style={{ 
          position: 'absolute', bottom: 30, left: '50%', transform: 'translateX(-50%)', 
          width: 400, background: 'rgba(0,0,0,0.7)', border: '1px solid #00ffff', 
          borderRadius: 8, padding: 20, backdropFilter: 'blur(10px)', textAlign: 'center',
          boxShadow: '0 0 30px rgba(0,255,255,0.1)'
        }}>
          <div style={{ fontSize: 9, color: '#00ffff', textTransform: 'uppercase', marginBottom: 8 }}>Body in Focus</div>
          <div style={{ fontSize: 20, color: '#fff', marginBottom: 12, fontWeight: 500 }}>{focusedNode.name}</div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 20 }}>
             <div className="muted" style={{ fontSize: 12 }}>Cognitive Debt: <span style={{ color: focusedNode.debt > 50 ? '#ff3333' : '#00ffaa' }}>{focusedNode.debt?.toFixed(1)}%</span></div>
             <div className="muted" style={{ fontSize: 12 }}>Status: <span style={{ color: '#00ffff' }}>Synchronized</span></div>
          </div>
        </div>
      )}

      {loading && <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', color: '#00ffff', fontWeight: 'bold' }}>BOOTING TELESCOPE...</div>}
    </div>
  )
}
