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
import { usePlayground } from '../hooks/usePlayground'
import type { ArchEdge, ArchNode, FunctionRef, Overview, TreeNode } from '../types/api'

// Node kinds that map to something the playground backend can actually
// import and run. Anything else (Directory/File/Module/Repository/Other)
// is structural and has no callable entry point. The set is intentionally
// narrow — broaden in a follow-up PR if symbol-level nodes start exposing
// Trait/Interface/etc. callables.
//
// TODO(#104): Atlas3D's buildFlowData currently emits only structural
// nodes (Repository/Directory/File/Module/Other), so this filter never
// matches in the live UI and the playground button stays disabled. The
// connector activates the moment Function/Method/Class nodes reach
// FlowData — see issue #104 for the data-layer work that unblocks it.
const LAUNCHABLE_NODE_TYPES: ReadonlySet<string> = new Set(['Function', 'Method', 'Class'])

// FlowNode.path encodes either a project-relative file path
// (e.g. "src/copyclip/foo.py") or — once symbol-level nodes are added —
// a "file:line" pair. Module nodes use a "module:<dotted>" prefix that
// we never reach here because LAUNCHABLE_NODE_TYPES filters them out.
function buildLaunchableRef(node: { name: string; path: string }): FunctionRef {
  const colon = node.path.indexOf(':')
  if (colon > 0) {
    const lineNum = Number(node.path.slice(colon + 1))
    return {
      file: node.path.slice(0, colon),
      name: node.name,
      line: Number.isFinite(lineNum) && lineNum > 0 ? lineNum : undefined,
    }
  }
  return { file: node.path, name: node.name }
}

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
  Method: '#9ccc65',
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
  // Modules whose symbol children have not been fetched yet (state ≠ 'loaded').
  // The expand affordance still renders for these so the user can trigger the
  // lazy fetch; the label shows `+` (unknown count) instead of `+N`.
  pendingModuleIds: ReadonlySet<number>
  // Fired the first time a pending Module is expanded. The page wires this
  // to a fetch against /api/module/symbols and merges the response into the
  // data on the next render.
  onModuleExpand: (moduleNodeId: number, modulePath: string) => void
}

type FlowEdgeInfo = {
  key: string
  type: string
  sourceId: number
  targetId: number
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
  { data, width, height, nodeColors, edgeColors, isDark, selectedId, onSelectNode, pendingModuleIds, onModuleExpand },
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

  // One-shot initialization: when data first becomes non-empty, seed
  // `expanded` with the auto-expand-on-load policy. Subsequent data growth
  // (e.g. lazy symbol fetch from #110's Module → Function/Method/Class
  // expansion) must NOT re-fire this effect — otherwise the Module the
  // user just clicked gets re-collapsed the moment its symbols arrive,
  // and the view jumps back to the autoFit baseline.
  const hasInitializedExpand = useRef(false)
  useEffect(() => {
    if (hasInitializedExpand.current) return
    if (data.nodes.length === 0) return
    setExpanded(initialExpanded)
    hasInitializedExpand.current = true
  }, [data.nodes.length, initialExpanded])

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
        out.push({ key: link.key, type: link.type, sourceId: link.sourceId, targetId: link.targetId, ...cached })
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
      out.push({ key: link.key, type: link.type, sourceId: link.sourceId, targetId: link.targetId, ...next })
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

  const focusId = hoverNode ?? selectedId
  const connectedIds = useMemo(() => {
    if (focusId == null) return null
    const set = new Set<number>([focusId])
    visibleLinks.forEach((link) => {
      if (link.sourceId === focusId) set.add(link.targetId)
      if (link.targetId === focusId) set.add(link.sourceId)
    })
    return set
  }, [focusId, visibleLinks])

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
    // Compute fetch intent BEFORE the updater — setExpanded's updater must
    // stay pure because React strict mode invokes it twice in development,
    // and calling onModuleExpand inside would fire the request twice.
    const wasExpanded = expanded.has(id)
    const node = nodeMap.get(id)
    const willTriggerFetch =
      !wasExpanded && node != null && node.type === 'Module' && pendingModuleIds.has(id)
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
    if (willTriggerFetch && node) {
      // The button stays as `+` (via the totalChildren === 0 branch below)
      // until the response merges children into `data`; no spinner — by design
      // the canvas keeps motion budget for the graph itself, not the node chrome.
      onModuleExpand(id, node.path)
    }
  }, [expanded, nodeMap, pendingModuleIds, onModuleExpand])

  // Pending Modules still show the expand affordance even though childMap has
  // no entries for them yet — that's how the user discovers there's something
  // to fetch.
  const hasChildren = useCallback(
    (id: number) =>
      pendingModuleIds.has(id) || (childMap.get(id) || []).some((childId) => nodeMap.has(childId)),
    [childMap, nodeMap, pendingModuleIds],
  )
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
          const touchesFocus = connectedIds == null || edge.sourceId === focusId || edge.targetId === focusId
          const opacity = (selected ? 1 : hovered ? 0.95 : contains ? 0.7 : 0.85) * (touchesFocus ? 1 : 0.2)

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
          const dimmed = connectedIds != null && !connectedIds.has(id)

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
              opacity={dimmed ? 0.15 : 1}
              style={{ cursor: dragId === id ? 'grabbing' : 'pointer', transition: 'opacity .15s' }}
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
                    {expandedNode
                      ? '−'
                      : pendingModuleIds.has(id) && totalChildren === 0
                        ? '+'
                        : `+${totalChildren}`}
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
  // Per-module symbol cache for the lazy Module → Function/Method/Class expand.
  // `idle` = fetch in flight, `loaded` = response merged (possibly with zero
  // symbols). Absence = never requested → pending → shows `+` affordance.
  const [moduleSymbolStates, setModuleSymbolStates] = useState<Map<number, 'idle' | 'loaded'>>(
    () => new Map(),
  )
  const [moduleSymbolChildren, setModuleSymbolChildren] = useState<Map<number, FlowNode[]>>(
    () => new Map(),
  )
  // Monotonically decreasing counter that hands out unique IDs for fetched
  // symbol nodes. Negatives never collide with `buildFlowData`'s positive
  // `nextId` allocation, so the merged FlowData can use plain numeric IDs.
  const symbolIdCounterRef = useRef(-1)

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
        setError(nextError instanceof Error ? nextError.message : 'Failed to load codebase map')
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

  // Reset the symbol cache whenever a fresh graph arrives (re-analyze, project
  // switch). The fetched Function/Method/Class IDs would otherwise dangle.
  useEffect(() => {
    setModuleSymbolStates(new Map())
    setModuleSymbolChildren(new Map())
    symbolIdCounterRef.current = -1
  }, [baseData])

  const fetchModuleSymbols = useCallback(
    async (moduleNodeId: number, modulePath: string) => {
      if (moduleSymbolStates.has(moduleNodeId)) return
      const dotted = modulePath.startsWith('module:')
        ? modulePath.slice('module:'.length)
        : modulePath
      if (!dotted) return
      setModuleSymbolStates((prev) => {
        const next = new Map(prev)
        next.set(moduleNodeId, 'idle')
        return next
      })
      try {
        const response = await api.moduleSymbols(dotted)
        const symbolNodes: FlowNode[] = []
        for (const symbol of response.symbols) {
          const kindCap =
            symbol.kind.charAt(0).toUpperCase() + symbol.kind.slice(1)
          if (kindCap !== 'Function' && kindCap !== 'Method' && kindCap !== 'Class') continue
          symbolNodes.push({
            id: symbolIdCounterRef.current,
            name: symbol.name,
            type: kindCap as FlowNodeType,
            path: `${symbol.file_path}:${symbol.line_start}`,
          })
          symbolIdCounterRef.current -= 1
        }
        setModuleSymbolChildren((prev) => {
          const next = new Map(prev)
          next.set(moduleNodeId, symbolNodes)
          return next
        })
        setModuleSymbolStates((prev) => {
          const next = new Map(prev)
          next.set(moduleNodeId, 'loaded')
          return next
        })
      } catch (err) {
        // Silent retry per the UX brief: no spinner, no error glyph. Drop the
        // pending state so the next click re-attempts the fetch.
        console.error('[atlas] module symbol fetch failed', dotted, err)
        setModuleSymbolStates((prev) => {
          const next = new Map(prev)
          next.delete(moduleNodeId)
          return next
        })
      }
    },
    [moduleSymbolStates],
  )

  const mergedData = useMemo<FlowData>(() => {
    if (moduleSymbolChildren.size === 0) return filteredData
    const newNodes = [...filteredData.nodes]
    const newLinks = [...filteredData.links]
    const parentIdsInData = new Set(filteredData.nodes.map((node) => node.id))
    const query = searchQuery.trim().toLowerCase()
    for (const [moduleId, symbolNodes] of moduleSymbolChildren) {
      if (!parentIdsInData.has(moduleId)) continue
      for (const symbolNode of symbolNodes) {
        if (!visibleNodeTypes.has(symbolNode.type)) continue
        if (
          query &&
          !symbolNode.name.toLowerCase().includes(query) &&
          !symbolNode.path.toLowerCase().includes(query)
        ) {
          continue
        }
        newNodes.push(symbolNode)
        newLinks.push({ source: moduleId, target: symbolNode.id, type: 'CONTAINS' })
      }
    }
    return { nodes: newNodes, links: newLinks }
  }, [filteredData, moduleSymbolChildren, visibleNodeTypes, searchQuery])

  const pendingModuleIds = useMemo(() => {
    const ids = new Set<number>()
    for (const node of mergedData.nodes) {
      if (node.type === 'Module' && moduleSymbolStates.get(node.id) !== 'loaded') {
        ids.add(node.id)
      }
    }
    return ids
  }, [mergedData.nodes, moduleSymbolStates])

  useEffect(() => {
    if (selectedNodeId == null) return
    if (!mergedData.nodes.some((node) => node.id === selectedNodeId)) setSelectedNodeId(null)
  }, [mergedData.nodes, selectedNodeId])

  const selectedNode = useMemo(
    () => mergedData.nodes.find((node) => node.id === selectedNodeId) || null,
    [mergedData.nodes, selectedNodeId],
  )

  const playground = usePlayground()
  // Carry the narrowed node (or null) explicitly so TS sees a non-null
  // FlowNode in every branch that consumes it — avoids the
  // `selectedNode!.name` non-null assertions that the previous shape needed.
  //
  // Python-only gate: Marimo (the playground engine) runs Python in v1. A
  // selection from a .ts/.tsx/.js file would reach `/api/playground/launch`
  // with a module like 'frontend/src/pages', fail the importable-module
  // check in resolve_function_ref (playground.py:310), and surface as a
  // misleading "function_not_found" dialog. We gate at the source so the
  // pill stays inert and the tooltip explains why.
  const isPythonSymbolPath = (path: string) => {
    const colon = path.indexOf(':')
    const filePath = colon > 0 ? path.slice(0, colon) : path
    return filePath.toLowerCase().endsWith('.py')
  }
  const isLaunchableType = selectedNode != null && LAUNCHABLE_NODE_TYPES.has(selectedNode.type)
  const launchableSelection =
    isLaunchableType && selectedNode != null && isPythonSymbolPath(selectedNode.path)
      ? selectedNode
      : null
  const launchPlayground = useCallback(() => {
    if (!launchableSelection) return
    void playground.launch({
      source: 'atlas',
      function_ref: buildLaunchableRef(launchableSelection),
      breadcrumb: `Atlas → ${launchableSelection.path} → ${launchableSelection.name}()`,
    })
  }, [launchableSelection, playground])

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
          <div className="atlas-flow-brand-title">Codebase Map</div>
        </div>

        <div className="atlas-flow-toolbar">
          <button className="atlas-flow-pill atlas-flow-icon-pill" onClick={() => setIsDark((value) => !value)} title="Toggle theme">
            {isDark ? '☼' : '◐'}
          </button>

          <button
            type="button"
            className="atlas-flow-pill"
            onClick={launchPlayground}
            disabled={launchableSelection == null}
            aria-label={
              launchableSelection
                ? `Open ${launchableSelection.name} in playground`
                : 'Open in Playground'
            }
            title={
              launchableSelection
                ? `Run ${launchableSelection.name}() in a Marimo playground`
                : isLaunchableType
                  ? 'Playground is Python-only in v1 — select a function from a .py file'
                  : 'Select a function, method, or class to open in the playground'
            }
            style={{
              borderColor: launchableSelection ? 'var(--accent-cyan)' : undefined,
              color: launchableSelection ? 'var(--accent-cyan)' : undefined,
              cursor: launchableSelection ? 'pointer' : 'not-allowed',
              opacity: launchableSelection ? 1 : 0.55,
            }}
          >
            <span aria-hidden="true">▶</span>&nbsp;Playground
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
            data={mergedData}
            width={viewport.width}
            height={viewport.height}
            nodeColors={DEFAULT_NODE_COLORS}
            edgeColors={DEFAULT_EDGE_COLORS}
            isDark={isDark}
            selectedId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
            pendingModuleIds={pendingModuleIds}
            onModuleExpand={fetchModuleSymbols}
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
