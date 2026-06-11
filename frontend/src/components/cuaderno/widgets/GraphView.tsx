import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import type { GraphViewWidget, Citation } from '../../../types/api'
import { fogFill, fogBorder, relativeBand } from '../../../utils/debt'
import { t } from '../strings'

// ── layout constants (roster-ratified for frame-scale use) ──────────────────
const LEVEL_GAP = 150
const NODE_W = 140
const NODE_H = 32
const NODE_V_GAP = 14
const CONTAINER_H = 420
const ZOOM_MIN = 0.75
const ZOOM_MAX = 2.0

type NodePos = { x: number; y: number }

type Props = {
  widget: GraphViewWidget
  onOpenCitation: (c: Citation) => void
  lang?: string | null
}

export function GraphView({ widget, onOpenCitation, lang }: Props) {
  const { nodes, edges } = widget

  // Heat is banded RELATIVE to the scores shown, so the hottest node paints
  // brightest even when the absolute distribution is compressed.
  const measuredScores = nodes
    .map((n) => n.heat)
    .filter((s): s is number => typeof s === 'number')
  const heatMin = measuredScores.length ? Math.min(...measuredScores) : 0
  const heatMax = measuredScores.length ? Math.max(...measuredScores) : 0

  // ── adjacency ─────────────────────────────────────────────────────────────
  const outgoing = useMemo(() => {
    const map = new Map<string, string[]>()
    nodes.forEach((n) => map.set(n.id, []))
    edges.forEach((e) => {
      if (!map.has(e.from)) map.set(e.from, [])
      map.get(e.from)!.push(e.to)
    })
    return map
  }, [nodes, edges])

  const incomingCount = useMemo(() => {
    const cnt = new Map<string, number>()
    nodes.forEach((n) => cnt.set(n.id, 0))
    edges.forEach((e) => cnt.set(e.to, (cnt.get(e.to) ?? 0) + 1))
    return cnt
  }, [nodes, edges])

  // ── layout: recursive place() with cycle guard ────────────────────────────
  // Roots = nodes with no incoming edges; fallback = first node (cycle-only graphs)
  const positions = useMemo(() => {
    const placed = new Set<string>()
    const pos = new Map<string, NodePos>()

    // determine placement children: outgoing targets not yet placed (checked at call time)
    const place = (id: string, depth: number, yCursor: { value: number }) => {
      if (placed.has(id)) return
      placed.add(id)
      const x = depth * (NODE_W + LEVEL_GAP)
      const y = yCursor.value
      pos.set(id, { x, y })
      yCursor.value += NODE_H + NODE_V_GAP

      const children = (outgoing.get(id) ?? []).filter((tid) => !placed.has(tid))
      children.forEach((childId) => place(childId, depth + 1, yCursor))
    }

    const roots = nodes
      .filter((n) => (incomingCount.get(n.id) ?? 0) === 0)
      .map((n) => n.id)

    const startRoots = roots.length > 0 ? roots : nodes.length > 0 ? [nodes[0].id] : []

    const yCursor = { value: 0 }
    startRoots.forEach((rootId) => {
      if (!placed.has(rootId)) place(rootId, 0, yCursor)
    })

    // disconnected or cycle-remnant nodes: wrap into columns rather than a single ribbon
    const unplaced = nodes.filter((n) => !placed.has(n.id))
    if (unplaced.length > 0) {
      let maxDepth = 0
      pos.forEach((p) => {
        const col = Math.round(p.x / (NODE_W + LEVEL_GAP))
        if (col > maxDepth) maxDepth = col
      })
      const orphanX = (maxDepth + 1) * (NODE_W + LEVEL_GAP)
      // how many rows fit in the placed tree's height (or CONTAINER_H if nothing placed)
      const treeHeight = yCursor.value > 0 ? yCursor.value : CONTAINER_H
      const maxRows = Math.max(1, Math.floor(treeHeight / (NODE_H + NODE_V_GAP)))
      unplaced.forEach((n, i) => {
        const row = i % maxRows
        const col = Math.floor(i / maxRows)
        pos.set(n.id, {
          x: orphanX + col * (NODE_W + 40),
          y: row * (NODE_H + NODE_V_GAP),
        })
      })
    }

    return pos
  }, [nodes, outgoing, incomingCount])

  // ── placed-child set for straight-vs-bezier decision ──────────────────────
  // An edge is a "direct tree edge" if target is NOT the source of a back/cross-edge
  // (simpler heuristic: edge is direct-tree if the edge goes to a target
  //  whose x == source.x + NODE_W + LEVEL_GAP — i.e., exactly one column right)
  const isDirectEdge = useCallback(
    (from: string, to: string) => {
      const s = positions.get(from)
      const t2 = positions.get(to)
      if (!s || !t2) return false
      return Math.abs(t2.x - (s.x + NODE_W + LEVEL_GAP)) < 2
    },
    [positions],
  )

  // ── graph bounding box ────────────────────────────────────────────────────
  const graphBounds = useMemo(() => {
    let minX = 0,
      minY = 0,
      maxX = NODE_W,
      maxY = NODE_H
    positions.forEach((p) => {
      minX = Math.min(minX, p.x)
      minY = Math.min(minY, p.y)
      maxX = Math.max(maxX, p.x + NODE_W)
      maxY = Math.max(maxY, p.y + NODE_H)
    })
    return { minX, minY, w: maxX - minX, h: maxY - minY }
  }, [positions])

  // ── focus / dim ───────────────────────────────────────────────────────────
  const [focus, setFocus] = useState<string | null>(widget.focus ?? null)

  const connectedToFocus = useMemo(() => {
    if (!focus) return null
    const set = new Set<string>([focus])
    edges.forEach((e) => {
      if (e.from === focus) set.add(e.to)
      if (e.to === focus) set.add(e.from)
    })
    return set
  }, [focus, edges])

  // ── pan / zoom ────────────────────────────────────────────────────────────
  const containerRef = useRef<HTMLDivElement>(null)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const isPanning = useRef(false)
  const panStart = useRef({ x: 0, y: 0, px: 0, py: 0 })
  const autoFitDone = useRef(false)

  // reset view state when the widget identity changes (new graph loaded)
  const widgetRef = useRef(widget)
  useEffect(() => {
    if (widgetRef.current !== widget) {
      widgetRef.current = widget
      autoFitDone.current = false
      setZoom(1)
      setPan({ x: 0, y: 0 })
      setFocus(widget.focus ?? null)
    }
  }, [widget])

  // auto-fit after first layout
  useEffect(() => {
    if (autoFitDone.current || positions.size === 0) return
    const containerW = containerRef.current?.clientWidth ?? 596
    const containerH = CONTAINER_H
    const fitZoom = Math.min(1, containerW / graphBounds.w, containerH / graphBounds.h)
    const clampedZoom = Math.max(ZOOM_MIN, fitZoom)
    setZoom(clampedZoom)
    // center the graph
    const centerX = graphBounds.minX + graphBounds.w / 2
    const centerY = graphBounds.minY + graphBounds.h / 2
    setPan({ x: -centerX, y: -centerY })
    autoFitDone.current = true
  }, [positions, graphBounds])

  // ctrl/cmd+wheel zoom — non-passive native listener so preventDefault() works in Chrome
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const handler = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return   // plain wheel: page scrolls, untouched
      e.preventDefault()
      setZoom((z) => Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z * (e.deltaY > 0 ? 0.92 : 1.08))))
    }
    el.addEventListener('wheel', handler, { passive: false })
    return () => el.removeEventListener('wheel', handler)
  }, [])

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      // only pan on background (svg itself) — node clicks are handled on the rects
      if ((e.target as SVGElement).tagName !== 'svg') return
      setFocus(null)
      isPanning.current = true
      panStart.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y }
      ;(e.currentTarget as SVGElement).setPointerCapture(e.pointerId)
    },
    [pan],
  )

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!isPanning.current) return
    setPan({
      x: panStart.current.px + (e.clientX - panStart.current.x) / zoom,
      y: panStart.current.py + (e.clientY - panStart.current.y) / zoom,
    })
  }, [zoom])

  const handlePointerUp = useCallback(() => {
    isPanning.current = false
  }, [])

  // ── node map for quick lookup ──────────────────────────────────────────────
  const nodeById = useMemo(
    () => new Map(nodes.map((n) => [n.id, n])),
    [nodes],
  )

  // ── SVG viewport transform ────────────────────────────────────────────────
  // We keep a fixed viewBox centered at 0,0 and apply pan+zoom as a group transform
  const viewSize = 596 // nominal width; height=CONTAINER_H
  const transform = `translate(${viewSize / 2 + pan.x * zoom} ${CONTAINER_H / 2 + pan.y * zoom}) scale(${zoom})`

  return (
    <div className="widget">
      <div className="widget-head">
        <span>
          <span className="kind">widget</span> · graph view
        </span>
        <span>{`${nodes.length} nodes · ${edges.length} edges`}</span>
      </div>
      <div className="graph-view" ref={containerRef}>
        <svg
          width="100%"
          height={CONTAINER_H}
          viewBox={`0 0 ${viewSize} ${CONTAINER_H}`}
          style={{ display: 'block', cursor: isPanning.current ? 'grabbing' : 'grab' }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
        >
          <g transform={transform}>
            {/* ── edges ── */}
            {edges.map((edge, i) => {
              const s = positions.get(edge.from)
              const t2 = positions.get(edge.to)
              if (!s || !t2) return null

              const dimEdge = connectedToFocus
                ? !connectedToFocus.has(edge.from) || !connectedToFocus.has(edge.to)
                : false
              const opacity = dimEdge ? 0.2 : 0.7

              const x1 = s.x + NODE_W
              const y1 = s.y + NODE_H / 2
              const x2 = t2.x
              const y2 = t2.y + NODE_H / 2

              let d: string
              if (isDirectEdge(edge.from, edge.to)) {
                // straight horizontal connector
                d = `M ${x1} ${y1} L ${x2} ${y2}`
              } else {
                // Bezier cross-link (from Atlas FlowchartCanvas edge math)
                const dx = Math.max(40, Math.abs(x2 - x1) * 0.45)
                d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
              }

              return (
                <path
                  key={i}
                  d={d}
                  fill="none"
                  stroke="var(--ink-3)"
                  strokeWidth={1.5}
                  opacity={opacity}
                  markerEnd="url(#arrowhead)"
                />
              )
            })}

            {/* ── nodes ── */}
            {nodes.map((node) => {
              const p = positions.get(node.id)
              if (!p) return null

              const isFocused = focus === node.id
              const isDimmed = connectedToFocus ? !connectedToFocus.has(node.id) : false
              const nodeOpacity = isDimmed ? 0.15 : 1

              // Cyan debt fog (neutral data, not alert), three honest states:
              //   number -> painted by its severity band (measured debt)
              //   null   -> dashed third state ("unmeasured" — never reads as low)
              //   absent -> plain node (a symbol/non-fog node; no debt concept)
              // A focused node shows selection (accent) over the fog.
              const score = node.heat
              const band = typeof score === 'number' ? relativeBand(score, heatMin, heatMax) : null
              const unmeasured = score === null
              const fill = isFocused
                ? 'var(--accent)'
                : band
                ? fogFill({ severity: band })
                : 'var(--surface)'
              const stroke = isFocused
                ? 'var(--accent-ink)'
                : band
                ? fogBorder({ severity: band })
                : 'var(--hairline)'
              const strokeDasharray = !isFocused && unmeasured ? '3 2' : undefined
              const textColor = isFocused ? 'var(--paper)' : 'var(--ink-2)'

              const label =
                node.label.length > 18 ? node.label.slice(0, 17) + '…' : node.label

              return (
                <g
                  key={node.id}
                  opacity={nodeOpacity}
                  style={{ cursor: 'pointer' }}
                  onClick={(e) => {
                    e.stopPropagation()
                    setFocus(focus === node.id ? null : node.id)
                  }}
                >
                  <rect
                    x={p.x}
                    y={p.y}
                    width={NODE_W}
                    height={NODE_H}
                    rx={4}
                    ry={4}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth={1}
                    strokeDasharray={strokeDasharray}
                  >
                    <title>{node.label}</title>
                  </rect>
                  <text
                    x={p.x + NODE_W / 2}
                    y={p.y + NODE_H / 2}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontFamily="var(--font-ui)"
                    fontSize={11}
                    fill={textColor}
                    style={{ pointerEvents: 'none', userSelect: 'none' }}
                  >
                    {label}
                  </text>
                  {/* citation chip: small underline strip at the bottom of the node */}
                  {node.citation ? (
                    <rect
                      x={p.x + NODE_W - 18}
                      y={p.y + NODE_H - 5}
                      width={14}
                      height={3}
                      rx={1.5}
                      fill={isFocused ? 'var(--paper)' : 'var(--accent)'}
                      opacity={0.7}
                      style={{ cursor: 'pointer' }}
                      onClick={(e) => {
                        e.stopPropagation()
                        onOpenCitation(node.citation!)
                      }}
                    />
                  ) : null}
                </g>
              )
            })}
          </g>

          {/* arrowhead marker */}
          <defs>
            <marker
              id="arrowhead"
              markerWidth={6}
              markerHeight={6}
              refX={5}
              refY={3}
              orient="auto"
            >
              <path d="M 0 0 L 6 3 L 0 6 z" fill="var(--ink-3)" />
            </marker>
          </defs>
        </svg>
      </div>
      {widget.truncated ? (
        <div className="graph-view-note">
          {t('graph_truncated', lang)}
        </div>
      ) : null}
    </div>
  )
}
