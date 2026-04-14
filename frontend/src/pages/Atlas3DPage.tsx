import { useEffect, useMemo, useRef, useState } from 'react'
// @ts-ignore - d3-force-3d has no type declarations
import { forceSimulation, forceManyBody, forceCenter, forceCollide, forceLink } from 'd3-force-3d'
import { api } from '../api/client'
import type {
  ArchEdge,
  ArchNode,
  CognitiveLoadItem,
  ModuleSourceFile,
  Overview,
  SymbolItem,
  TreeNode,
} from '../types/api'

type GraphNode = {
  id: string
  label: string
  path: string
  kind: 'module' | 'folder' | 'file'
  group: string
  degree: number
  debt: number
  size: number
  modulePath: string
}

type GraphEdge = {
  id: string
  source: string
  target: string
  type: 'import' | 'contains'
}

type GraphDataset = {
  nodes: GraphNode[]
  edges: GraphEdge[]
  source: 'dependencies' | 'tree'
}

type Viewport = { x: number; y: number; k: number }

const CANVAS_WIDTH = 1200
const CANVAS_HEIGHT = 760

const GROUP_COLORS: Record<string, string> = {
  intelligence: '#67e8f9',
  llm: '#f59e0b',
  frontend: '#86efac',
  tests: '#fda4af',
  docs: '#c4b5fd',
  scripts: '#fdba74',
  config: '#94a3b8',
  root: '#e5e7eb',
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function getLeafLabel(path: string) {
  if (!path) return 'root'
  const pieces = path.split('/')
  return pieces[pieces.length - 1] || path
}

function getGroup(value: string) {
  const lower = value.toLowerCase()
  if (lower.includes('frontend')) return 'frontend'
  if (lower.includes('intelligence')) return 'intelligence'
  if (lower.includes('/llm') || lower.startsWith('copyclip/llm') || lower.startsWith('src/copyclip/llm')) return 'llm'
  if (lower.includes('test')) return 'tests'
  if (lower.includes('docs')) return 'docs'
  if (lower.includes('script')) return 'scripts'
  if (lower.startsWith('.') || lower.includes('package') || lower.includes('pyproject') || lower.includes('requirements')) return 'config'
  return 'root'
}

function getDebtColor(debt: number) {
  if (debt >= 70) return '#f87171'
  if (debt >= 45) return '#fbbf24'
  return '#67e8f9'
}

function collectTreeNodes(root: TreeNode | null) {
  if (!root) return []
  const out: TreeNode[] = []
  const walk = (node: TreeNode) => {
    out.push(node)
    ;(node.children || []).forEach(walk)
  }
  walk(root)
  return out
}

function findTreeNode(root: TreeNode | null, modulePath: string) {
  const nodes = collectTreeNodes(root)
  const exact = nodes.find((node) => node.path === modulePath)
  if (exact) return exact
  const suffix = nodes.find((node) => node.path && (node.path.endsWith(modulePath) || modulePath.endsWith(node.path)))
  if (suffix) return suffix
  return nodes.find((node) => node.name === getLeafLabel(modulePath)) || null
}

function buildDependencyGraph(
  tree: TreeNode | null,
  rawNodes: ArchNode[],
  rawEdges: ArchEdge[],
  cognitiveMap: Map<string, CognitiveLoadItem>,
) {
  const candidates = rawNodes
    .map((node) => {
      const treeNode = findTreeNode(tree, node.name)
      if (!treeNode && node.name !== 'root') return null
      const cognitive = cognitiveMap.get(node.name)
      const debt = cognitive?.cognitive_debt_score || treeNode?.debt || treeNode?.avg_debt || 0
      return {
        id: node.name,
        label: getLeafLabel(node.name),
        path: node.name,
        kind: 'module' as const,
        group: getGroup(node.name),
        degree: 0,
        debt,
        size: 18,
        modulePath: node.name,
      }
    })
    .filter(Boolean) as GraphNode[]

  const nodeIds = new Set(candidates.map((node) => node.id))
  const edges = rawEdges
    .filter((edge) => nodeIds.has(edge.from) && nodeIds.has(edge.to) && edge.from !== edge.to)
    .map((edge) => ({
      id: `${edge.from}__${edge.to}`,
      source: edge.from,
      target: edge.to,
      type: 'import' as const,
    }))

  const degreeMap = new Map<string, number>()
  candidates.forEach((node) => degreeMap.set(node.id, 0))
  edges.forEach((edge) => {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1)
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1)
  })

  const nodes = candidates.map((node) => {
    const degree = degreeMap.get(node.id) || 0
    return {
      ...node,
      degree,
      size: clamp(10 + Math.sqrt(Math.max(degree, 1)) * 4, 10, 28),
    }
  })

  if (nodes.length < 3 || edges.length < 2) return null
  return { nodes, edges, source: 'dependencies' as const }
}

function buildTreeGraph(tree: TreeNode | null) {
  if (!tree) {
    return { nodes: [] as GraphNode[], edges: [] as GraphEdge[], source: 'tree' as const }
  }

  const nodes: GraphNode[] = []
  const edges: GraphEdge[] = []
  let visibleFiles = 0

  const walk = (node: TreeNode, parent: TreeNode | null, depth: number) => {
    const path = node.path || node.name || 'root'
    const isRoot = node.name === 'root'
    const isHidden = node.name.startsWith('.') && !isRoot
    if (isHidden) return

    if (node.type === 'file') {
      if (visibleFiles >= 140) return
      visibleFiles += 1
    }

    if (depth > 4 && node.type === 'folder') return

    const sizeBase = node.type === 'folder' ? Math.log2((node.file_count || 1) + 2) * 3 : Math.log2((node.lines || 40) + 2)
    nodes.push({
      id: path,
      label: isRoot ? 'root' : node.name,
      path,
      kind: node.type === 'folder' ? 'folder' : 'file',
      group: getGroup(path),
      degree: 0,
      debt: node.debt || node.avg_debt || 0,
      size: clamp(sizeBase, node.type === 'folder' ? 10 : 7, node.type === 'folder' ? 20 : 15),
      modulePath: node.type === 'file'
        ? (path.includes('/') ? path.slice(0, path.lastIndexOf('/')) || 'root' : 'root')
        : path || 'root',
    })

    if (parent) {
      edges.push({
        id: `${parent.path || parent.name}__${path}`,
        source: parent.path || parent.name,
        target: path,
        type: 'contains',
      })
    }

    ;(node.children || []).forEach((child) => walk(child, node, depth + 1))
  }

  walk(tree, null, 0)

  const degreeMap = new Map<string, number>()
  nodes.forEach((node) => degreeMap.set(node.id, 0))
  edges.forEach((edge) => {
    degreeMap.set(edge.source, (degreeMap.get(edge.source) || 0) + 1)
    degreeMap.set(edge.target, (degreeMap.get(edge.target) || 0) + 1)
  })

  return {
    nodes: nodes.map((node) => ({ ...node, degree: degreeMap.get(node.id) || 0 })),
    edges,
    source: 'tree' as const,
  }
}

function makeDataset(
  tree: TreeNode | null,
  rawNodes: ArchNode[],
  rawEdges: ArchEdge[],
  cognitiveMap: Map<string, CognitiveLoadItem>,
) {
  return buildDependencyGraph(tree, rawNodes, rawEdges, cognitiveMap) || buildTreeGraph(tree)
}

function localGraph(dataset: GraphDataset, centerId: string | null, depth: number) {
  if (!centerId) return dataset
  const adjacency = new Map<string, Set<string>>()
  dataset.nodes.forEach((node) => adjacency.set(node.id, new Set()))
  dataset.edges.forEach((edge) => {
    adjacency.get(edge.source)?.add(edge.target)
    adjacency.get(edge.target)?.add(edge.source)
  })

  const keep = new Set<string>([centerId])
  let frontier = new Set<string>([centerId])
  for (let level = 0; level < depth; level += 1) {
    const next = new Set<string>()
    frontier.forEach((id) => {
      adjacency.get(id)?.forEach((neighbor) => {
        if (!keep.has(neighbor)) {
          keep.add(neighbor)
          next.add(neighbor)
        }
      })
    })
    frontier = next
  }

  return {
    ...dataset,
    nodes: dataset.nodes.filter((node) => keep.has(node.id)),
    edges: dataset.edges.filter((edge) => keep.has(edge.source) && keep.has(edge.target)),
  }
}

function filteredGraph(dataset: GraphDataset, search: string, showOrphans: boolean) {
  const term = search.trim().toLowerCase()
  const matchedNodes = dataset.nodes.filter((node) => {
    if (!term) return true
    return node.label.toLowerCase().includes(term) || node.path.toLowerCase().includes(term)
  })
  const keep = new Set(matchedNodes.map((node) => node.id))
  const edges = dataset.edges.filter((edge) => keep.has(edge.source) && keep.has(edge.target))

  if (showOrphans) {
    return { ...dataset, nodes: matchedNodes, edges }
  }

  const connected = new Set<string>()
  edges.forEach((edge) => {
    connected.add(edge.source)
    connected.add(edge.target)
  })

  return {
    ...dataset,
    nodes: matchedNodes.filter((node) => connected.has(node.id)),
    edges,
  }
}

function runLayout(dataset: GraphDataset, forces: { center: number; repel: number; link: number; distance: number }) {
  const simNodes = dataset.nodes.map((node) => ({ ...node, x: 0, y: 0, z: 0 }))
  const sim = forceSimulation(simNodes, 3)
    .force('charge', forceManyBody().strength(-Math.max(forces.repel, 10)))
    .force('center', forceCenter(0, 0, 0).strength(Math.max(forces.center, 0.01)))
    .force('collide', forceCollide().radius((node: GraphNode) => node.size + 12))
    .force(
      'link',
      forceLink(dataset.edges.map((edge) => ({ source: edge.source, target: edge.target })))
        .id((node: GraphNode) => node.id)
        .distance(Math.max(forces.distance, 20))
        .strength(Math.max(forces.link, 0.01)),
    )
    .stop()

  for (let i = 0; i < 240; i += 1) sim.tick()

  if (simNodes.length === 1) {
    return new Map([[simNodes[0].id, { x: CANVAS_WIDTH / 2, y: CANVAS_HEIGHT / 2 }]])
  }

  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity

  simNodes.forEach((node) => {
    minX = Math.min(minX, node.x)
    maxX = Math.max(maxX, node.x)
    minY = Math.min(minY, node.y)
    maxY = Math.max(maxY, node.y)
  })

  const spanX = Math.max(maxX - minX, 1)
  const spanY = Math.max(maxY - minY, 1)
  const positions = new Map<string, { x: number; y: number }>()
  simNodes.forEach((node) => {
    positions.set(node.id, {
      x: 80 + ((node.x - minX) / spanX) * (CANVAS_WIDTH - 160),
      y: 80 + ((node.y - minY) / spanY) * (CANVAS_HEIGHT - 160),
    })
  })
  return positions
}

export function Atlas3DPage() {
  const svgRef = useRef<SVGSVGElement>(null)
  const interactionRef = useRef<{ mode: 'pan' | 'drag'; id?: string; x: number; y: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [tree, setTree] = useState<TreeNode | null>(null)
  const [archNodes, setArchNodes] = useState<ArchNode[]>([])
  const [archEdges, setArchEdges] = useState<ArchEdge[]>([])
  const [cognitiveItems, setCognitiveItems] = useState<CognitiveLoadItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [localMode, setLocalMode] = useState(false)
  const [depth, setDepth] = useState(1)
  const [showOrphans, setShowOrphans] = useState(false)
  const [showLabels, setShowLabels] = useState(true)
  const [showArrows, setShowArrows] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [viewport, setViewport] = useState<Viewport>({ x: 0, y: 0, k: 1 })
  const [forces, setForces] = useState({ center: 1, repel: 260, link: 0.18, distance: 100, nodeScale: 1, linkWidth: 1.4, textFade: 0.22 })
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map())
  const [sourceFiles, setSourceFiles] = useState<ModuleSourceFile[]>([])
  const [symbols, setSymbols] = useState<SymbolItem[]>([])
  const [activeFileIdx, setActiveFileIdx] = useState(0)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const codeMirrorRef = useRef<HTMLDivElement>(null)
  const cmInstanceRef = useRef<any>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [overviewRes, treeRes, graphRes, cognitiveRes] = await Promise.all([
          api.overview(),
          api.architectureTree(),
          api.architecture(),
          api.cognitiveLoad(),
        ])
        if (cancelled) return
        setOverview(overviewRes)
        setTree(treeRes)
        setArchNodes(graphRes.nodes)
        setArchEdges(graphRes.edges)
        setCognitiveItems(cognitiveRes.items || [])
        setError(null)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Atlas failed to load')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const cognitiveMap = useMemo(() => new Map(cognitiveItems.map((item) => [item.module, item])), [cognitiveItems])
  const baseDataset = useMemo(() => makeDataset(tree, archNodes, archEdges, cognitiveMap), [tree, archNodes, archEdges, cognitiveMap])
  const activeId = selectedId || hoveredId || baseDataset.nodes[0]?.id || null
  const step1 = useMemo(() => filteredGraph(baseDataset, search, showOrphans), [baseDataset, search, showOrphans])
  const visibleDataset = useMemo(
    () => (localMode ? localGraph(step1, activeId, depth) : step1),
    [step1, localMode, activeId, depth],
  )

  useEffect(() => {
    const nextId = visibleDataset.nodes.find((node) => node.id === selectedId)?.id || visibleDataset.nodes[0]?.id || null
    setSelectedId(nextId)
  }, [visibleDataset, selectedId])

  useEffect(() => {
    setPositions(runLayout(visibleDataset, forces))
  }, [visibleDataset, forces.center, forces.repel, forces.link, forces.distance])

  useEffect(() => {
    const selectedNode = visibleDataset.nodes.find((node) => node.id === selectedId)
    if (!selectedNode) {
      setSourceFiles([])
      setSymbols([])
      return
    }

    let cancelled = false
    setLoadingDetails(true)
    Promise.all([api.moduleSource(selectedNode.modulePath), api.moduleSymbols(selectedNode.modulePath)])
      .then(([sourceRes, symbolRes]) => {
        if (cancelled) return
        const files = sourceRes.files || []
        setSourceFiles(files)
        if (selectedNode.kind === 'file') {
          setSymbols((symbolRes.symbols || []).filter((item) => item.file_path === selectedNode.path))
          const idx = files.findIndex((file) => file.path === selectedNode.path)
          setActiveFileIdx(idx >= 0 ? idx : 0)
        } else {
          setSymbols(symbolRes.symbols || [])
          setActiveFileIdx(0)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSourceFiles([])
          setSymbols([])
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingDetails(false)
      })

    return () => {
      cancelled = true
    }
  }, [selectedId, visibleDataset.nodes])

  useEffect(() => {
    const file = sourceFiles[activeFileIdx]
    if (!file) return
    const timer = window.setTimeout(() => {
      const root = codeMirrorRef.current
      if (!root) return
      if (cmInstanceRef.current) {
        cmInstanceRef.current.toTextArea()
        cmInstanceRef.current = null
      }
      while (root.firstChild) root.removeChild(root.firstChild)
      const textarea = document.createElement('textarea')
      root.appendChild(textarea)
      const CodeMirror = (window as any).CodeMirror
      if (!CodeMirror) return
      cmInstanceRef.current = CodeMirror.fromTextArea(textarea, {
        value: file.content,
        mode: file.language || null,
        readOnly: true,
        lineNumbers: true,
        theme: 'atlas-cosmic',
      })
      cmInstanceRef.current.setValue(file.content)
    }, 40)
    return () => window.clearTimeout(timer)
  }, [sourceFiles, activeFileIdx])

  const activeNode = visibleDataset.nodes.find((node) => node.id === activeId) || null
  const connected = useMemo(() => {
    const set = new Set<string>()
    if (!activeId) return set
    set.add(activeId)
    visibleDataset.edges.forEach((edge) => {
      if (edge.source === activeId) set.add(edge.target)
      if (edge.target === activeId) set.add(edge.source)
    })
    return set
  }, [visibleDataset, activeId])

  const nodeById = useMemo(() => {
    const map = new Map<string, GraphNode>()
    visibleDataset.nodes.forEach((node) => map.set(node.id, node))
    return map
  }, [visibleDataset])

  const screenToWorld = (clientX: number, clientY: number) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    const sx = ((clientX - rect.left) / rect.width) * CANVAS_WIDTH
    const sy = ((clientY - rect.top) / rect.height) * CANVAS_HEIGHT
    return {
      x: (sx - viewport.x) / viewport.k,
      y: (sy - viewport.y) / viewport.k,
    }
  }

  const onWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    event.preventDefault()
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const px = ((event.clientX - rect.left) / rect.width) * CANVAS_WIDTH
    const py = ((event.clientY - rect.top) / rect.height) * CANVAS_HEIGHT
    const nextK = clamp(viewport.k * (event.deltaY > 0 ? 0.92 : 1.08), 0.35, 3.2)
    setViewport((current) => ({
      x: px - ((px - current.x) / current.k) * nextK,
      y: py - ((py - current.y) / current.k) * nextK,
      k: nextK,
    }))
  }

  const onPointerDownBackground = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.target !== event.currentTarget) return
    interactionRef.current = { mode: 'pan', x: event.clientX, y: event.clientY }
  }

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const interaction = interactionRef.current
    if (!interaction) return
    if (interaction.mode === 'pan') {
      const dx = ((event.clientX - interaction.x) / (svgRef.current?.getBoundingClientRect().width || 1)) * CANVAS_WIDTH
      const dy = ((event.clientY - interaction.y) / (svgRef.current?.getBoundingClientRect().height || 1)) * CANVAS_HEIGHT
      interactionRef.current = { ...interaction, x: event.clientX, y: event.clientY }
      setViewport((current) => ({ ...current, x: current.x + dx, y: current.y + dy }))
      return
    }
    if (interaction.mode === 'drag' && interaction.id) {
      const world = screenToWorld(event.clientX, event.clientY)
      setPositions((current) => new Map(current).set(interaction.id!, world))
    }
  }

  const clearInteraction = () => {
    interactionRef.current = null
  }

  const onNodePointerDown = (event: React.PointerEvent<SVGGElement>, id: string) => {
    event.stopPropagation()
    interactionRef.current = { mode: 'drag', id, x: event.clientX, y: event.clientY }
  }

  const resetView = () => {
    setViewport({ x: 0, y: 0, k: 1 })
    setPositions(runLayout(visibleDataset, forces))
  }

  const jumpToSymbol = (symbol: SymbolItem) => {
    const fileIdx = sourceFiles.findIndex((file) => file.path === symbol.file_path)
    if (fileIdx >= 0) setActiveFileIdx(fileIdx)
    window.setTimeout(() => {
      cmInstanceRef.current?.scrollIntoView({ line: Math.max(symbol.line_start - 1, 0), ch: 0 }, 120)
      cmInstanceRef.current?.setCursor({ line: Math.max(symbol.line_start - 1, 0), ch: 0 })
    }, 140)
  }

  return (
    <div className="atlas-shell">
      <div className="atlas-toolbar">
        <div className="atlas-toolbar-left">
          <div>
            <div className="muted atlas-toolbar-kicker">// atlas_graph</div>
            <h1>Atlas</h1>
          </div>
          <div className="atlas-toolbar-meta">
            <span>{baseDataset.source === 'dependencies' ? 'dependency graph' : 'tree graph'}</span>
            <span>{visibleDataset.nodes.length} nodes</span>
            <span>{visibleDataset.edges.length} links</span>
            <span>{overview?.modules || 0} indexed modules</span>
          </div>
        </div>

        <div className="atlas-toolbar-actions">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search files or modules"
            className="atlas-search"
          />
          <button className={`atlas-toggle${localMode ? ' atlas-toggle--active' : ''}`} onClick={() => setLocalMode((value) => !value)}>
            Local graph
          </button>
          <button className="atlas-toggle" onClick={resetView}>Reset view</button>
          <button className={`atlas-toggle${showSettings ? ' atlas-toggle--active' : ''}`} onClick={() => setShowSettings((value) => !value)}>
            Settings
          </button>
        </div>
      </div>

      {loading ? (
        <div className="atlas-loading">Loading graph…</div>
      ) : error ? (
        <div className="error">{error}</div>
      ) : (
        <div className="atlas-grid">
          <section className="atlas-graph-panel">
            <div className="atlas-panel-head">
              <div className="atlas-panel-title">Graph</div>
              <div className="atlas-panel-caption">Hover to highlight, drag nodes, wheel to zoom, drag canvas to pan</div>
            </div>

            <div className="atlas-graph-controls">
              {localMode && (
                <label className="atlas-inline-control">
                  <span>Depth</span>
                  <input type="range" min="1" max="4" value={depth} onChange={(event) => setDepth(Number(event.target.value))} />
                  <strong>{depth}</strong>
                </label>
              )}
              <label className="atlas-inline-check">
                <input type="checkbox" checked={showOrphans} onChange={(event) => setShowOrphans(event.target.checked)} />
                <span>Show orphans</span>
              </label>
              <label className="atlas-inline-check">
                <input type="checkbox" checked={showLabels} onChange={(event) => setShowLabels(event.target.checked)} />
                <span>Labels</span>
              </label>
              <label className="atlas-inline-check">
                <input type="checkbox" checked={showArrows} onChange={(event) => setShowArrows(event.target.checked)} />
                <span>Arrows</span>
              </label>
            </div>

            {showSettings && (
              <div className="atlas-settings-panel">
                <label className="atlas-range">
                  <span>Center force</span>
                  <input type="range" min="0.2" max="3" step="0.1" value={forces.center} onChange={(event) => setForces((current) => ({ ...current, center: Number(event.target.value) }))} />
                </label>
                <label className="atlas-range">
                  <span>Repel force</span>
                  <input type="range" min="40" max="600" step="10" value={forces.repel} onChange={(event) => setForces((current) => ({ ...current, repel: Number(event.target.value) }))} />
                </label>
                <label className="atlas-range">
                  <span>Link force</span>
                  <input type="range" min="0.05" max="1" step="0.01" value={forces.link} onChange={(event) => setForces((current) => ({ ...current, link: Number(event.target.value) }))} />
                </label>
                <label className="atlas-range">
                  <span>Link distance</span>
                  <input type="range" min="40" max="180" step="5" value={forces.distance} onChange={(event) => setForces((current) => ({ ...current, distance: Number(event.target.value) }))} />
                </label>
                <label className="atlas-range">
                  <span>Node size</span>
                  <input type="range" min="0.6" max="2" step="0.05" value={forces.nodeScale} onChange={(event) => setForces((current) => ({ ...current, nodeScale: Number(event.target.value) }))} />
                </label>
                <label className="atlas-range">
                  <span>Link thickness</span>
                  <input type="range" min="0.6" max="3" step="0.1" value={forces.linkWidth} onChange={(event) => setForces((current) => ({ ...current, linkWidth: Number(event.target.value) }))} />
                </label>
                <label className="atlas-range">
                  <span>Text fade</span>
                  <input type="range" min="0" max="0.9" step="0.05" value={forces.textFade} onChange={(event) => setForces((current) => ({ ...current, textFade: Number(event.target.value) }))} />
                </label>
              </div>
            )}

            <div className="atlas-graph-frame atlas-graph-frame--obsidian">
              <svg
                ref={svgRef}
                className="atlas-graph-svg"
                viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`}
                onWheel={onWheel}
                onPointerDown={onPointerDownBackground}
                onPointerMove={onPointerMove}
                onPointerUp={clearInteraction}
                onPointerLeave={clearInteraction}
              >
                <defs>
                  <marker id="atlas-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
                    <path d="M0,0 L7,3.5 L0,7 z" fill="rgba(103, 232, 249, 0.8)" />
                  </marker>
                </defs>
                <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.k})`}>
                  {visibleDataset.edges.map((edge) => {
                    const source = positions.get(edge.source)
                    const target = positions.get(edge.target)
                    if (!source || !target) return null
                    const active = activeId && (edge.source === activeId || edge.target === activeId)
                    const faded = activeId && !active
                    return (
                      <line
                        key={edge.id}
                        x1={source.x}
                        y1={source.y}
                        x2={target.x}
                        y2={target.y}
                        className={`atlas-edge${active ? ' atlas-edge--active' : ''}${faded ? ' atlas-edge--faded' : ''}`}
                        strokeWidth={forces.linkWidth}
                        markerEnd={showArrows && edge.type === 'import' ? 'url(#atlas-arrow)' : undefined}
                      />
                    )
                  })}

                  {visibleDataset.nodes.map((node) => {
                    const pos = positions.get(node.id)
                    if (!pos) return null
                    const active = activeId === node.id
                    const adjacent = connected.has(node.id)
                    const faded = activeId && !adjacent
                    const radius = node.size * forces.nodeScale
                    const labelOpacity = showLabels ? (active || adjacent ? 1 : 1 - forces.textFade) : 0
                    return (
                      <g
                        key={node.id}
                        transform={`translate(${pos.x}, ${pos.y})`}
                        className={`atlas-node${active ? ' atlas-node--active' : ''}${faded ? ' atlas-node--faded' : ''}`}
                        onPointerDown={(event) => onNodePointerDown(event, node.id)}
                        onMouseEnter={() => setHoveredId(node.id)}
                        onMouseLeave={() => setHoveredId((current) => (current === node.id ? null : current))}
                        onClick={(event) => {
                          event.stopPropagation()
                          setSelectedId(node.id)
                        }}
                      >
                        <circle className="atlas-node-ring" r={radius + 5} fill="transparent" stroke={getDebtColor(node.debt)} strokeOpacity="0.15" />
                        <circle r={radius} fill={GROUP_COLORS[node.group] || GROUP_COLORS.root} stroke={active ? '#ffffff' : getDebtColor(node.debt)} strokeWidth={active ? 2 : 1.1} />
                        {showLabels && (
                          <text y={radius + 16} textAnchor="middle" style={{ opacity: labelOpacity }}>
                            {node.label}
                          </text>
                        )}
                      </g>
                    )
                  })}
                </g>
              </svg>
            </div>
          </section>

          <aside className="atlas-inspector">
            <section className="atlas-card atlas-card--compact">
              <div className="atlas-panel-head">
                <div className="atlas-panel-title">Selection</div>
              </div>
              {activeNode ? (
                <>
                  <h2 className="atlas-node-title">{activeNode.path}</h2>
                  <div className="atlas-inspector-grid">
                    <div>
                      <span>Type</span>
                      <strong>{activeNode.kind}</strong>
                    </div>
                    <div>
                      <span>Group</span>
                      <strong>{activeNode.group}</strong>
                    </div>
                    <div>
                      <span>Degree</span>
                      <strong>{activeNode.degree}</strong>
                    </div>
                    <div>
                      <span>Debt</span>
                      <strong style={{ color: getDebtColor(activeNode.debt) }}>{Math.round(activeNode.debt)}%</strong>
                    </div>
                  </div>
                </>
              ) : (
                <div className="muted">No node selected.</div>
              )}
            </section>

            <section className="atlas-card atlas-card--compact">
              <div className="atlas-panel-head">
                <div className="atlas-panel-title">Neighbors</div>
              </div>
              <div className="atlas-chip-list">
                {activeNode ? (
                  visibleDataset.edges
                    .filter((edge) => edge.source === activeNode.id || edge.target === activeNode.id)
                    .map((edge) => {
                      const otherId = edge.source === activeNode.id ? edge.target : edge.source
                      const other = nodeById.get(otherId)
                      if (!other) return null
                      return (
                        <button key={edge.id} className="atlas-chip" onClick={() => setSelectedId(other.id)}>
                          {other.label}
                        </button>
                      )
                    })
                ) : (
                  <span className="muted">No neighbors.</span>
                )}
              </div>
            </section>

            <section className="atlas-card atlas-card--compact">
              <div className="atlas-panel-head">
                <div className="atlas-panel-title">Symbols</div>
              </div>
              <div className="atlas-symbol-list">
                {symbols.length > 0 ? (
                  symbols.slice(0, 16).map((symbol) => (
                    <button key={`${symbol.file_path}-${symbol.name}`} className="atlas-symbol-row" onClick={() => jumpToSymbol(symbol)}>
                      <span>{symbol.name}</span>
                      <small>{symbol.kind}</small>
                    </button>
                  ))
                ) : (
                  <div className="muted">{loadingDetails ? 'Loading symbols…' : 'No symbols available.'}</div>
                )}
              </div>
            </section>

            <section className="atlas-card atlas-card--compact atlas-code-card">
              <div className="atlas-panel-head">
                <div className="atlas-panel-title">Code</div>
                <div className="atlas-panel-caption">{loadingDetails ? 'loading…' : ''}</div>
              </div>
              {sourceFiles.length > 0 ? (
                <>
                  <div className="atlas-file-tabs">
                    {sourceFiles.map((file, index) => (
                      <button
                        key={file.path}
                        className={`atlas-file-tab${index === activeFileIdx ? ' atlas-file-tab--active' : ''}`}
                        onClick={() => setActiveFileIdx(index)}
                      >
                        {getLeafLabel(file.path)}
                      </button>
                    ))}
                  </div>
                  <div className="atlas-code-container" ref={codeMirrorRef} />
                </>
              ) : (
                <div className="atlas-code-empty">No source preview available.</div>
              )}
            </section>
          </aside>
        </div>
      )}
    </div>
  )
}
