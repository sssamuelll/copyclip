import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react'
import { api } from '../api/client'
import type { ArchEdge, ArchNode, Overview, TreeNode } from '../types/api'

const NODE_W = 200
const NODE_H = 40
const LEVEL_GAP = 280
const NODE_GAP = 16
const SLOT_R = 3.5
const GITHUB_URL = 'https://github.com/sssamuelll/copyclip'

const DEFAULT_NODE_COLORS: Record<string, string> = {
  Repository: '#ffffff',
  Directory: '#f59e0b',
  File: '#42a5f5',
  Class: '#66bb6a',
  Interface: '#26a69a',
  Trait: '#81c784',
  Function: '#ffca28',
  Module: '#ef5350',
  Variable: '#ffa726',
  Enum: '#7e57c2',
  Struct: '#5c6bc0',
  Macro: '#ff7043',
  Record: '#4db6ac',
  Union: '#8d6e63',
  Property: '#dce775',
  Annotation: '#ec407a',
  Parameter: '#90a4ae',
  Other: '#78909c',
}

const DEFAULT_EDGE_COLORS: Record<string, string> = {
  CONTAINS: '#ffffff',
  CALLS: '#ab47bc',
  IMPORTS: '#42a5f5',
  INHERITS: '#66bb6a',
  IMPLEMENTS: '#26a69a',
  INCLUDES: '#81c784',
  HAS_PARAMETER: '#ffca28',
}

const COLLAPSE_THRESHOLD = 14
const COLLAPSE_CHUNK_SIZE = 12

type FlowNodeType = keyof typeof DEFAULT_NODE_COLORS
type FlowEdgeType = keyof typeof DEFAULT_EDGE_COLORS

type FlowNode = {
  id: number
  name: string
  type: FlowNodeType
  path: string
}

type FlowLink = {
  source: number
  target: number
  type: FlowEdgeType
}

type FlowData = {
  nodes: FlowNode[]
  links: FlowLink[]
}

type FlowHandle = {
  zoomIn: () => void
  zoomOut: () => void
  fitView: () => void
}

type FlowchartCanvasProps = {
  data: FlowData
  width: number
  height: number
  nodeColors: Record<string, string>
  edgeColors: Record<string, string>
  isDark: boolean
  selectedId: number | null
  onSelectNode: (id: number | null) => void
}

type FlowEdgeInfo = {
  key: string
  type: string
  d: string
  mx: number
  my: number
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function normalizePath(value: string) {
  return value.replace(/\\/g, '/').replace(/^\.?\//, '').replace(/\/+/g, '/')
}

function isHiddenPath(value: string) {
  const normalized = normalizePath(value)
  if (!normalized || normalized === 'root') return false
  return normalized.split('/').some((segment) => segment.startsWith('.'))
}

function getLeafLabel(path: string) {
  if (!path) return 'root'
  const pieces = normalizePath(path).split('/')
  return pieces[pieces.length - 1] || path
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

function findTreeNode(root: TreeNode | null, targetPath: string) {
  const normalizedTarget = normalizePath(targetPath)
  const nodes = collectTreeNodes(root)
  return (
    nodes.find((node) => normalizePath(node.path) === normalizedTarget) ||
    nodes.find((node) => normalizePath(node.path).endsWith(normalizedTarget) || normalizedTarget.endsWith(normalizePath(node.path))) ||
    nodes.find((node) => node.name === getLeafLabel(normalizedTarget)) ||
    null
  )
}

function mapEdgeType(type: string): FlowEdgeType {
  const upper = type.toUpperCase()
  if (upper.includes('CALL')) return 'CALLS'
  if (upper.includes('INHERIT')) return 'INHERITS'
  if (upper.includes('IMPLEMENT')) return 'IMPLEMENTS'
  if (upper.includes('INCLUDE')) return 'INCLUDES'
  if (upper.includes('PARAM')) return 'HAS_PARAMETER'
  return 'IMPORTS'
}

function buildFlowData(tree: TreeNode | null, archNodes: ArchNode[], archEdges: ArchEdge[]): FlowData {
  const nodes: FlowNode[] = []
  const links: FlowLink[] = []
  const pathToId = new Map<string, number>()
  const moduleToId = new Map<string, number>()
  const nodeIndexById = new Map<number, number>()
  const maxFiles = 220
  let nextId = 1
  let visibleFiles = 0

  const addNode = (path: string, name: string, type: FlowNodeType) => {
    const normalizedPath = normalizePath(path)
    const existing = pathToId.get(normalizedPath)
    if (existing) return existing
    const id = nextId
    nextId += 1
    pathToId.set(normalizedPath, id)
    nodes.push({ id, name, type, path: normalizedPath })
    nodeIndexById.set(id, nodes.length - 1)
    return id
  }

  const setNodeType = (id: number, type: FlowNodeType) => {
    const index = nodeIndexById.get(id)
    if (index == null) return
    nodes[index] = { ...nodes[index], type }
  }

  const addLink = (source: number, target: number, type: FlowEdgeType) => {
    if (source === target) return
    links.push({ source, target, type })
  }

  const rootId = addNode('root', 'root', 'Repository')

  const walkTree = (node: TreeNode, parentId: number, depth: number) => {
    const rawPath = node.path || node.name || 'root'
    const normalizedPath = rawPath === 'root' ? 'root' : normalizePath(rawPath)
    const isRoot = normalizedPath === 'root' || node.name === 'root'
    const isHidden = isHiddenPath(normalizedPath) && !isRoot

    if (isHidden) return
    if (depth > 6 && node.type === 'folder') return
    if (node.type === 'file') {
      if (visibleFiles >= maxFiles) return
      visibleFiles += 1
    }

    const ownId = isRoot
      ? rootId
      : addNode(normalizedPath, node.name || getLeafLabel(normalizedPath), node.type === 'folder' ? 'Directory' : 'File')

    if (!isRoot) addLink(parentId, ownId, 'CONTAINS')

    ;(node.children || []).forEach((child) => walkTree(child, ownId, depth + 1))
  }

  if (tree) walkTree(tree, rootId, 0)

  archNodes.forEach((node) => {
    const normalizedName = normalizePath(node.name)
    if (!normalizedName || normalizedName === 'root' || isHiddenPath(normalizedName)) return
    const existingId = pathToId.get(normalizedName)
    if (existingId) {
      if (nodes[nodeIndexById.get(existingId) || 0]?.type === 'Directory') setNodeType(existingId, 'Module')
      moduleToId.set(node.name, existingId)
      return
    }
    const owner = findTreeNode(tree, normalizedName)
    const ownerPath = owner?.path ? normalizePath(owner.path) : 'root'
    const ownerId = pathToId.get(ownerPath) || rootId
    const id = addNode(`module:${normalizedName}`, getLeafLabel(normalizedName), 'Module')
    moduleToId.set(node.name, id)
    addLink(ownerId, id, 'CONTAINS')
  })

  archEdges.forEach((edge) => {
    const sourceId = moduleToId.get(edge.from)
    const targetId = moduleToId.get(edge.to)
    if (!sourceId || !targetId) return
    addLink(sourceId, targetId, mapEdgeType(edge.type))
  })

  const dedupedLinks = new Map<string, FlowLink>()
  links.forEach((link) => {
    const key = `${link.source}:${link.target}:${link.type}`
    if (!dedupedLinks.has(key)) dedupedLinks.set(key, link)
  })
  let normalizedLinks = [...dedupedLinks.values()]

  const addNormalizedLink = (source: number, target: number, type: FlowEdgeType) => {
    if (source === target) return
    if (!normalizedLinks.some((link) => link.source === source && link.target === target && link.type === type)) {
      normalizedLinks.push({ source, target, type })
    }
  }

  const ensureDirectoryChain = (directoryPath: string) => {
    const normalized = normalizePath(directoryPath)
    if (!normalized || normalized === 'root') return rootId
    const existing = pathToId.get(normalized)
    if (existing) return existing

    const parts = normalized.split('/').filter(Boolean)
    let parentId = rootId
    let currentPath = ''
    parts.forEach((part) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part
      const knownId = pathToId.get(currentPath)
      if (knownId) {
        parentId = knownId
        return
      }
      const nextId = addNode(currentPath, part, 'Directory')
      addNormalizedLink(parentId, nextId, 'CONTAINS')
      parentId = nextId
    })
    return parentId
  }

  const rewireContainsParents = () => {
    const parentByChild = new Map<number, number>()
    normalizedLinks.forEach((link) => {
      if (link.type === 'CONTAINS') parentByChild.set(link.target, link.source)
    })

    nodes.forEach((node) => {
      if (node.type !== 'File') return
      const parentPath = normalizePath(node.path.split('/').slice(0, -1).join('/'))
      const desiredParent = parentPath ? ensureDirectoryChain(parentPath) : rootId
      const currentParent = parentByChild.get(node.id)
      if (currentParent === desiredParent) return
      normalizedLinks = normalizedLinks.filter((link) => !(link.type === 'CONTAINS' && link.target === node.id))
      addNormalizedLink(desiredParent, node.id, 'CONTAINS')
      parentByChild.set(node.id, desiredParent)
    })
  }

  const collapseLargeSiblingSets = () => {
    const childMap = new Map<number, number[]>()
    normalizedLinks.forEach((link) => {
      if (link.type !== 'CONTAINS') return
      if (!childMap.has(link.source)) childMap.set(link.source, [])
      childMap.get(link.source)?.push(link.target)
    })

    childMap.forEach((childIds, parentId) => {
      const collapsible = childIds
        .map((id) => nodes[nodeIndexById.get(id) ?? -1])
        .filter((node): node is FlowNode => Boolean(node))
        .filter((node) => node.type === 'File' || node.type === 'Module')
        .sort((a, b) => a.name.localeCompare(b.name))

      if (collapsible.length <= COLLAPSE_THRESHOLD) return

      const collapseIds = new Set(collapsible.map((node) => node.id))
      normalizedLinks = normalizedLinks.filter(
        (link) => !(link.type === 'CONTAINS' && link.source === parentId && collapseIds.has(link.target)),
      )

      for (let index = 0; index < collapsible.length; index += COLLAPSE_CHUNK_SIZE) {
        const chunk = collapsible.slice(index, index + COLLAPSE_CHUNK_SIZE)
        const label = `${chunk.length} children collapsed`
        const collapsedId = addNode(`collapsed:${parentId}:${index}`, label, 'Other')
        normalizedLinks.push({ source: parentId, target: collapsedId, type: 'CONTAINS' })
        chunk.forEach((node) => {
          normalizedLinks.push({ source: collapsedId, target: node.id, type: 'CONTAINS' })
        })
      }
    })
  }

  rewireContainsParents()
  collapseLargeSiblingSets()

  const finalLinks = new Map<string, FlowLink>()
  normalizedLinks.forEach((link) => {
    const key = `${link.source}:${link.target}:${link.type}`
    if (!finalLinks.has(key)) finalLinks.set(key, link)
  })

  return { nodes, links: [...finalLinks.values()] }
}

const FlowchartCanvas = forwardRef<FlowHandle, FlowchartCanvasProps>(function FlowchartCanvas(
  { data, width, height, nodeColors, edgeColors, isDark, selectedId, onSelectNode },
  ref,
) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set())
  const [positions, setPositions] = useState<Map<number, { x: number; y: number }>>(new Map())
  const [hoverEdge, setHoverEdge] = useState<string | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null)
  const [hoverNode, setHoverNode] = useState<number | null>(null)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(0.65)
  const [dragId, setDragId] = useState<number | null>(null)
  const [showOrphans, setShowOrphans] = useState(false)
  const isPanning = useRef(false)
  const panStart = useRef({ x: 0, y: 0, px: 0, py: 0 })
  const dragStart = useRef<{ mx: number; my: number; nx: number; ny: number } | null>(null)
  const autoFitDone = useRef(false)
  const pathCache = useRef<Map<string, { d: string; mx: number; my: number }>>(new Map())

  const childMap = useMemo(() => {
    const map = new Map<number, number[]>()
    data.links.forEach((link) => {
      if (link.type !== 'CONTAINS') return
      if (!map.has(link.source)) map.set(link.source, [])
      map.get(link.source)?.push(link.target)
    })
    return map
  }, [data.links])

  const parentMap = useMemo(() => {
    const map = new Map<number, number>()
    data.links.forEach((link) => {
      if (link.type === 'CONTAINS') map.set(link.target, link.source)
    })
    return map
  }, [data.links])

  const crossLinks = useMemo(
    () => data.links.filter((link) => link.type !== 'CONTAINS'),
    [data.links],
  )

  const nodeMap = useMemo(() => {
    const map = new Map<number, FlowNode>()
    data.nodes.forEach((node) => map.set(node.id, node))
    return map
  }, [data.nodes])

  const roots = useMemo(
    () => data.nodes.filter((node) => !parentMap.has(node.id)).map((node) => node.id),
    [data.nodes, parentMap],
  )

  const initialExpanded = useMemo(() => {
    const next = new Set<number>()
    roots.forEach((rootId) => {
      const children = childMap.get(rootId) || []
      if (children.length <= 10) next.add(rootId)
    })
    return next
  }, [roots, childMap])

  useEffect(() => {
    setExpanded(initialExpanded)
    setSelectedEdge(null)
    setHoverEdge(null)
    setHoverNode(null)
    autoFitDone.current = false
  }, [initialExpanded, data.nodes.length, data.links.length])

  const orphanIds = useMemo(
    () => new Set(roots.filter((id) => !(childMap.get(id) || []).some((childId) => nodeMap.has(childId)))),
    [roots, childMap, nodeMap],
  )

  const visibleIds = useMemo(() => {
    const visible = new Set<number>()
    const queue = [...roots]
    while (queue.length) {
      const id = queue.shift()
      if (id == null || !nodeMap.has(id)) continue
      if (orphanIds.has(id) && !showOrphans) continue
      visible.add(id)
      if (expanded.has(id)) (childMap.get(id) || []).forEach((childId) => queue.push(childId))
    }
    return visible
  }, [roots, nodeMap, orphanIds, showOrphans, expanded, childMap])

  useEffect(() => {
    const subtreeHeight = (id: number): number => {
      if (!expanded.has(id) || !visibleIds.has(id)) return NODE_H
      const kids = (childMap.get(id) || []).filter((kidId) => visibleIds.has(kidId))
      if (!kids.length) return NODE_H
      return kids.reduce((sum, kidId) => sum + subtreeHeight(kidId) + NODE_GAP, -NODE_GAP)
    }

    const nextPositions = new Map<number, { x: number; y: number }>()

    const place = (id: number, x: number, yCenter: number) => {
      nextPositions.set(id, { x, y: yCenter - NODE_H / 2 })
      if (!expanded.has(id)) return
      const kids = (childMap.get(id) || []).filter((kidId) => visibleIds.has(kidId))
      if (!kids.length) return
      const total = subtreeHeight(id)
      let offsetY = yCenter - total / 2
      kids.forEach((kidId) => {
        const kidHeight = subtreeHeight(kidId)
        place(kidId, x + LEVEL_GAP, offsetY + kidHeight / 2)
        offsetY += kidHeight + NODE_GAP
      })
    }

    const treeRoots = roots.filter((id) => visibleIds.has(id) && !orphanIds.has(id))
    const totalHeight = treeRoots.reduce((sum, id) => sum + subtreeHeight(id) + NODE_GAP * 3, 0)
    let y = -totalHeight / 2
    treeRoots.forEach((id) => {
      const rootHeight = subtreeHeight(id)
      place(id, 40, y + rootHeight / 2)
      y += rootHeight + NODE_GAP * 3
    })

    if (showOrphans) {
      const orphans = roots.filter((id) => orphanIds.has(id) && visibleIds.has(id))
      let maxX = 40
      nextPositions.forEach((position) => {
        if (position.x + NODE_W > maxX) maxX = position.x + NODE_W
      })
      const orphanStartX = maxX + LEVEL_GAP
      const cols = 2
      const colWidth = NODE_W + 20
      const rowHeight = NODE_H + NODE_GAP
      const gridTop = -totalHeight / 2
      orphans.forEach((id, index) => {
        const col = index % cols
        const row = Math.floor(index / cols)
        nextPositions.set(id, { x: orphanStartX + col * colWidth, y: gridTop + row * rowHeight })
      })
    }

    pathCache.current.clear()
    setPositions(nextPositions)
  }, [visibleIds, expanded, childMap, roots, orphanIds, showOrphans])

  const visibleLinks = useMemo(() => {
    const out: Array<{ key: string; sourceId: number; targetId: number; type: string }> = []
    visibleIds.forEach((id) => {
      if (!expanded.has(id)) return
      ;(childMap.get(id) || [])
        .filter((kidId) => visibleIds.has(kidId))
        .forEach((kidId) =>
          out.push({
            key: `c-${id}-${kidId}`,
            sourceId: id,
            targetId: kidId,
            type: 'CONTAINS',
          }),
        )
    })
    crossLinks.forEach((link) => {
      if (visibleIds.has(link.source) && visibleIds.has(link.target)) {
        out.push({
          key: `x-${link.source}-${link.target}-${link.type}`,
          sourceId: link.source,
          targetId: link.target,
          type: link.type,
        })
      }
    })
    return out
  }, [visibleIds, expanded, childMap, crossLinks])

  const edges = useMemo((): FlowEdgeInfo[] => {
    const out: FlowEdgeInfo[] = []
    visibleLinks.forEach((link) => {
      const sourcePosition = positions.get(link.sourceId)
      const targetPosition = positions.get(link.targetId)
      if (!sourcePosition || !targetPosition) return

      const cacheKey = `${link.key}:${sourcePosition.x}:${sourcePosition.y}:${targetPosition.x}:${targetPosition.y}`
      const cached = pathCache.current.get(cacheKey)
      if (cached) {
        out.push({ key: link.key, type: link.type, ...cached })
        return
      }

      const x1 = sourcePosition.x + NODE_W
      const y1 = sourcePosition.y + NODE_H / 2
      const x2 = targetPosition.x
      const y2 = targetPosition.y + NODE_H / 2
      const dx = Math.max(40, (x2 - x1) * 0.45)
      const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
      const mx = (x1 + x2) / 2
      const my = (y1 + y2) / 2
      const next = { d, mx, my }
      pathCache.current.set(cacheKey, next)
      out.push({ key: link.key, type: link.type, ...next })
    })
    return out
  }, [visibleLinks, positions])

  const sortedEdges = useMemo(
    () =>
      [...edges].sort((a, b) => {
        if (a.key === selectedEdge) return 1
        if (b.key === selectedEdge) return -1
        if (a.key === hoverEdge) return 1
        if (b.key === hoverEdge) return -1
        return a.type === 'CONTAINS' ? -1 : 1
      }),
    [edges, selectedEdge, hoverEdge],
  )

  const fitView = useCallback(() => {
    if (!visibleIds.size || !positions.size) {
      setPan({ x: 0, y: 0 })
      setZoom(0.65)
      return
    }

    let minX = Number.POSITIVE_INFINITY
    let minY = Number.POSITIVE_INFINITY
    let maxX = Number.NEGATIVE_INFINITY
    let maxY = Number.NEGATIVE_INFINITY

    visibleIds.forEach((id) => {
      const position = positions.get(id)
      if (!position) return
      minX = Math.min(minX, position.x)
      minY = Math.min(minY, position.y)
      maxX = Math.max(maxX, position.x + NODE_W)
      maxY = Math.max(maxY, position.y + NODE_H)
    })

    if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
      setPan({ x: 0, y: 0 })
      setZoom(0.65)
      return
    }

    const graphWidth = maxX - minX || NODE_W
    const graphHeight = maxY - minY || NODE_H
    const nextZoom = clamp(Math.min((width - 160) / graphWidth, (height - 140) / graphHeight), 0.12, 1.4)
    const centerX = minX + graphWidth / 2
    const centerY = minY + graphHeight / 2
    setZoom(nextZoom)
    setPan({ x: -centerX, y: -centerY })
  }, [height, positions, visibleIds, width])

  useEffect(() => {
    if (positions.size === 0 || autoFitDone.current) return
    fitView()
    autoFitDone.current = true
  }, [positions, fitView])

  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => setZoom((value) => clamp(value * 1.12, 0.04, 4)),
      zoomOut: () => setZoom((value) => clamp(value * 0.9, 0.04, 4)),
      fitView,
    }),
    [fitView],
  )

  useEffect(() => {
    const element = svgRef.current
    if (!element) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      setZoom((value) => clamp(value * (event.deltaY > 0 ? 0.92 : 1.08), 0.04, 4))
    }
    element.addEventListener('wheel', onWheel, { passive: false })
    return () => element.removeEventListener('wheel', onWheel)
  }, [])

  const onBackgroundDown = useCallback(
    (event: React.MouseEvent) => {
      onSelectNode(null)
      isPanning.current = true
      panStart.current = { x: event.clientX, y: event.clientY, px: pan.x, py: pan.y }
    },
    [onSelectNode, pan],
  )

  const onMouseMove = useCallback(
    (event: React.MouseEvent) => {
      if (isPanning.current) {
        setPan({
          x: panStart.current.px + (event.clientX - panStart.current.x) / zoom,
          y: panStart.current.py + (event.clientY - panStart.current.y) / zoom,
        })
      }
      if (dragId !== null && dragStart.current) {
        const dx = (event.clientX - dragStart.current.mx) / zoom
        const dy = (event.clientY - dragStart.current.my) / zoom
        setPositions((current) => {
          const next = new Map(current)
          next.set(dragId, { x: dragStart.current!.nx + dx, y: dragStart.current!.ny + dy })
          return next
        })
      }
    },
    [dragId, zoom],
  )

  const onMouseUp = useCallback(() => {
    isPanning.current = false
    setDragId(null)
    dragStart.current = null
  }, [])

  const grabNode = useCallback(
    (id: number, event: React.MouseEvent) => {
      event.stopPropagation()
      isPanning.current = false
      const position = positions.get(id)
      if (!position) return
      setDragId(id)
      dragStart.current = { mx: event.clientX, my: event.clientY, nx: position.x, ny: position.y }
    },
    [positions],
  )

  const toggleExpand = useCallback((id: number, event: React.MouseEvent) => {
    event.stopPropagation()
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const hasChildren = useCallback((id: number) => (childMap.get(id) || []).some((childId) => nodeMap.has(childId)), [childMap, nodeMap])
  const childCount = useCallback((id: number) => (childMap.get(id) || []).filter((childId) => nodeMap.has(childId)).length, [childMap, nodeMap])

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      className="atlas-flow-svg"
      style={{ background: isDark ? '#020202' : '#f5f5f7', cursor: isPanning.current ? 'grabbing' : 'grab' }}
      onMouseDown={onBackgroundDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
    >
      <defs>
        <pattern
          id="atlas-flow-grid"
          width={40}
          height={40}
          patternUnits="userSpaceOnUse"
          patternTransform={`translate(${pan.x * zoom + width / 2},${pan.y * zoom + height / 2}) scale(${zoom})`}
        >
          <path d="M 40 0 L 0 0 0 40" fill="none" stroke={isDark ? '#0d0d14' : '#e5e5ea'} strokeWidth={0.6} />
        </pattern>
        <filter id="atlas-edgeglow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      <rect width={width} height={height} fill="url(#atlas-flow-grid)" style={{ pointerEvents: 'none' }} />

      <g transform={`translate(${width / 2 + pan.x * zoom},${height / 2 + pan.y * zoom}) scale(${zoom})`} style={{ pointerEvents: 'auto' }}>
        {sortedEdges.map((edge) => {
          const hovered = edge.key === hoverEdge
          const selected = edge.key === selectedEdge
          const contains = edge.type === 'CONTAINS'
          const baseColor = edgeColors[edge.type] || '#555'
          const color = selected ? '#fb923c' : hovered ? '#f59e0b' : contains ? (isDark ? '#4a4a5a' : '#9a9aaa') : baseColor
          const strokeWidth = selected ? 3 : hovered ? 2.5 : contains ? 1.6 : 2
          const opacity = selected ? 1 : hovered ? 0.95 : contains ? 0.7 : 0.85

          return (
            <g key={edge.key}>
              <path
                d={edge.d}
                fill="none"
                stroke="transparent"
                strokeWidth={14}
                onMouseEnter={() => setHoverEdge(edge.key)}
                onMouseLeave={() => setHoverEdge(null)}
                onClick={() => setSelectedEdge((value) => (value === edge.key ? null : edge.key))}
                style={{ cursor: 'pointer' }}
              >
                <title>{edge.type}</title>
              </path>
              <path
                d={edge.d}
                fill="none"
                stroke={color}
                strokeWidth={strokeWidth}
                opacity={opacity}
                strokeLinecap="round"
                filter={selected || hovered ? 'url(#atlas-edgeglow)' : undefined}
                strokeDasharray={contains ? undefined : '6 3'}
                style={{ pointerEvents: 'none', transition: 'stroke-width .15s, opacity .15s' }}
              />
              {(hovered || selected) && !contains && (
                <g style={{ pointerEvents: 'none' }}>
                  <rect
                    x={edge.mx - 34}
                    y={edge.my - 10}
                    width={68}
                    height={20}
                    rx={4}
                    fill={isDark ? '#0a0a12' : '#ffffff'}
                    stroke={color}
                    strokeWidth={0.8}
                    opacity={0.92}
                  />
                  <text
                    x={edge.mx}
                    y={edge.my + 1}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize={9}
                    fontWeight={700}
                    fontFamily="Inter,system-ui,sans-serif"
                    fill={color}
                    style={{ letterSpacing: '0.06em' }}
                  >
                    {edge.type}
                  </text>
                </g>
              )}
            </g>
          )
        })}

        {Array.from(visibleIds).map((id) => {
          const node = nodeMap.get(id)
          const position = positions.get(id)
          if (!node || !position) return null

          const color = nodeColors[node.type] || '#78909c'
          const hovered = id === hoverNode
          const expandedNode = expanded.has(id)
          const children = hasChildren(id)
          const totalChildren = childCount(id)
          const active = selectedId === id

          return (
            <g
              key={id}
              transform={`translate(${position.x},${position.y})`}
              onMouseDown={(event) => grabNode(id, event)}
              onMouseEnter={() => setHoverNode(id)}
              onMouseLeave={() => setHoverNode(null)}
              onClick={(event) => {
                event.stopPropagation()
                onSelectNode(id)
              }}
              style={{ cursor: dragId === id ? 'grabbing' : 'pointer' }}
            >
              {hovered && (
                <rect
                  x={-3}
                  y={-3}
                  width={NODE_W + 6}
                  height={NODE_H + 6}
                  rx={9}
                  fill="none"
                  stroke={color}
                  strokeWidth={1.5}
                  opacity={0.25}
                  filter="url(#atlas-edgeglow)"
                />
              )}
              <rect
                width={NODE_W}
                height={NODE_H}
                rx={6}
                fill={hovered ? (isDark ? '#181822' : '#f0f0f5') : (isDark ? '#0e0e14' : '#ffffff')}
                stroke={active ? '#f8fafc' : color}
                strokeWidth={active ? 1.9 : hovered ? 1.8 : 1}
                opacity={0.96}
              />
              <circle cx={0} cy={NODE_H / 2} r={SLOT_R} fill={color} opacity={0.5} />
              <circle cx={NODE_W} cy={NODE_H / 2} r={SLOT_R} fill={color} opacity={0.5} />
              <text
                x={12}
                y={16}
                fontSize={12}
                fontFamily="Inter,system-ui,sans-serif"
                fontWeight={600}
                fill={isDark ? '#d4d4d8' : '#1a1a1a'}
                style={{ pointerEvents: 'none' }}
              >
                {node.name.length > 22 ? `${node.name.slice(0, 20)}…` : node.name}
              </text>
              <text
                x={12}
                y={33}
                fontSize={8}
                fontFamily="Inter,system-ui,sans-serif"
                fontWeight={700}
                fill={color}
                opacity={0.55}
                style={{ pointerEvents: 'none', letterSpacing: '0.08em' }}
              >
                {node.type.toUpperCase()}
              </text>
              {children && (
                <g onClick={(event) => toggleExpand(id, event)} style={{ cursor: 'pointer' }}>
                  <rect
                    x={NODE_W - 30}
                    y={(NODE_H - 18) / 2}
                    width={24}
                    height={18}
                    rx={4}
                    fill={expandedNode ? `${color}22` : `${color}11`}
                    stroke={color}
                    strokeWidth={0.5}
                  />
                  <text
                    x={NODE_W - 18}
                    y={NODE_H / 2 + 1}
                    fontSize={11}
                    fontWeight={700}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill={color}
                    style={{ pointerEvents: 'none' }}
                  >
                    {expandedNode ? '−' : `+${totalChildren}`}
                  </text>
                </g>
              )}
            </g>
          )
        })}
      </g>

      {orphanIds.size > 0 && (
        <g transform={`translate(${width - 204}, 18)`} onClick={() => setShowOrphans((value) => !value)} style={{ cursor: 'pointer' }}>
          <rect
            width={186}
            height={28}
            rx={14}
            fill={showOrphans ? (isDark ? '#1e1e2e' : '#e8e8f0') : (isDark ? '#111118' : '#f0f0f5')}
            stroke={showOrphans ? '#f59e0b55' : (isDark ? '#ffffff18' : '#00000018')}
            strokeWidth={1}
          />
          <text
            x={93}
            y={15}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={10}
            fontWeight={700}
            fontFamily="Inter,system-ui,sans-serif"
            fill={showOrphans ? '#f59e0b' : (isDark ? '#666' : '#888')}
            style={{ letterSpacing: '0.06em' }}
          >
            {showOrphans ? `HIDE ${orphanIds.size} EXTERNAL` : `SHOW ${orphanIds.size} EXTERNAL`}
          </text>
        </g>
      )}
    </svg>
  )
})

export function Atlas3DPage() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [baseData, setBaseData] = useState<FlowData>({ nodes: [], links: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [isDark, setIsDark] = useState(true)
  const [legendCollapsed, setLegendCollapsed] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [visibleNodeTypes, setVisibleNodeTypes] = useState<Set<string>>(() => new Set(Object.keys(DEFAULT_NODE_COLORS)))
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null)
  const [viewport, setViewport] = useState({ width: 1200, height: 760 })
  const flowRef = useRef<FlowHandle | null>(null)

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      try {
        setLoading(true)
        const [nextOverview, tree, architecture] = await Promise.all([
          api.overview(),
          api.architectureTree(),
          api.architecture(),
        ])

        if (cancelled) return
        setOverview(nextOverview)
        setBaseData(buildFlowData(tree, architecture.nodes, architecture.edges))
        setError('')
      } catch (nextError) {
        if (cancelled) return
        setError(nextError instanceof Error ? nextError.message : 'Failed to load atlas graph')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const updateViewport = () => {
      const innerHeight = window.innerHeight - 48
      setViewport({ width: window.innerWidth - 280, height: Math.max(620, innerHeight) })
    }
    updateViewport()
    window.addEventListener('resize', updateViewport)
    return () => window.removeEventListener('resize', updateViewport)
  }, [])

  const filteredData = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    const keepNodes = baseData.nodes.filter((node) => {
      if (!visibleNodeTypes.has(node.type)) return false
      if (!query) return true
      return node.name.toLowerCase().includes(query) || node.path.toLowerCase().includes(query)
    })
    const keepIds = new Set(keepNodes.map((node) => node.id))
    const keepEdges = baseData.links.filter((link) => keepIds.has(link.source) && keepIds.has(link.target))
    return { nodes: keepNodes, links: keepEdges }
  }, [baseData, searchQuery, visibleNodeTypes])

  useEffect(() => {
    if (selectedNodeId == null) return
    if (!filteredData.nodes.some((node) => node.id === selectedNodeId)) setSelectedNodeId(null)
  }, [filteredData.nodes, selectedNodeId])

  const selectedNode = useMemo(
    () => filteredData.nodes.find((node) => node.id === selectedNodeId) || null,
    [filteredData.nodes, selectedNodeId],
  )

  const toggleNodeType = (type: string) => {
    setVisibleNodeTypes((current) => {
      const next = new Set(current)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  return (
    <section className={`atlas-flow-page${isDark ? ' atlas-flow-page--dark' : ''}`}>
      <div className="atlas-flow-topbar">
        <div className="atlas-flow-brand">
          <div className="atlas-flow-brand-kicker">{overview?.meta?.project || 'copyclip'}</div>
          <div className="atlas-flow-brand-title">Atlas Flowchart</div>
        </div>

        <div className="atlas-flow-toolbar">
          <button className="atlas-flow-pill atlas-flow-icon-pill" onClick={() => setIsDark((value) => !value)} title="Toggle theme">
            {isDark ? '☼' : '◐'}
          </button>

          <div className="atlas-flow-pill atlas-flow-mode-pill">
            <span className="atlas-flow-mode-dot" />
            <span>FLOWCHART</span>
          </div>

          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className="atlas-flow-search"
            placeholder="Search nodes"
          />

          <a className="atlas-flow-pill atlas-flow-link-pill" href={GITHUB_URL} target="_blank" rel="noreferrer">
            ★ STAR ON GITHUB
          </a>
        </div>
      </div>

      <div className="atlas-flow-stage">
        <div className="atlas-flow-controls">
          <button type="button" onClick={() => flowRef.current?.zoomIn()} title="Zoom in">＋</button>
          <button type="button" onClick={() => flowRef.current?.fitView()} title="Fit view">□</button>
          <button type="button" onClick={() => flowRef.current?.zoomOut()} title="Zoom out">－</button>
        </div>

        {loading ? (
          <div className="atlas-flow-state">Loading graph…</div>
        ) : error ? (
          <div className="atlas-flow-state atlas-flow-state--error">{error}</div>
        ) : (
          <FlowchartCanvas
            ref={flowRef}
            data={filteredData}
            width={viewport.width}
            height={viewport.height}
            nodeColors={DEFAULT_NODE_COLORS}
            edgeColors={DEFAULT_EDGE_COLORS}
            isDark={isDark}
            selectedId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
          />
        )}

        {selectedNode && (
          <div className="atlas-flow-selection">
            <span className="atlas-flow-selection-type">{selectedNode.type}</span>
            <strong>{selectedNode.name}</strong>
            <small>{selectedNode.path}</small>
          </div>
        )}

        {!showFilters && (
          <div className="atlas-flow-legend">
            <div className="atlas-flow-legend-header" onClick={() => setLegendCollapsed((value) => !value)}>
              <span>Graph Legend</span>
              <div className="atlas-flow-legend-actions">
                <button
                  type="button"
                  className="atlas-flow-filter-trigger"
                  onClick={(event) => {
                    event.stopPropagation()
                    setShowFilters(true)
                  }}
                >
                  Filters
                </button>
                <span className={`atlas-flow-chevron${legendCollapsed ? ' atlas-flow-chevron--collapsed' : ''}`}>⌃</span>
              </div>
            </div>
            {!legendCollapsed && (
              <div className="atlas-flow-legend-grid">
                {Object.keys(DEFAULT_NODE_COLORS).map((type) => (
                  <div key={type} className="atlas-flow-legend-item">
                    <span
                      className="atlas-flow-legend-dot"
                      style={{ backgroundColor: DEFAULT_NODE_COLORS[type], boxShadow: `0 0 8px ${DEFAULT_NODE_COLORS[type]}` }}
                    />
                    <span className={visibleNodeTypes.has(type) ? '' : 'atlas-flow-legend-item--muted'}>{type}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {showFilters && (
          <div className="atlas-flow-filter-panel">
            <div className="atlas-flow-legend-header">
              <span>Filters</span>
              <button type="button" className="atlas-flow-filter-close" onClick={() => setShowFilters(false)}>✕</button>
            </div>
            <div className="atlas-flow-filter-list">
              {Object.keys(DEFAULT_NODE_COLORS).map((type) => (
                <button key={type} type="button" className="atlas-flow-filter-row" onClick={() => toggleNodeType(type)}>
                  <div className="atlas-flow-filter-left">
                    <span className="atlas-flow-legend-dot" style={{ backgroundColor: DEFAULT_NODE_COLORS[type] }} />
                    <span>{type}</span>
                  </div>
                  <span className={`atlas-flow-filter-toggle${visibleNodeTypes.has(type) ? ' atlas-flow-filter-toggle--active' : ''}`}>
                    {visibleNodeTypes.has(type) ? 'ON' : 'OFF'}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
