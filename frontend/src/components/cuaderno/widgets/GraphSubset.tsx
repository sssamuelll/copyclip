import type { GraphSubsetWidget } from '../../../types/api'

type Props = { widget: GraphSubsetWidget }

export function GraphSubset({ widget }: Props) {
  const { nodes, edges } = widget
  // Positions: simple deterministic 2-column layout for Phase 1 display-only.
  // (Phase 2 will make this interactive; positions become dynamic.)
  const positioned = nodes.map((n, i) => ({
    ...n,
    x: 40 + (i % 3) * 160,
    y: 30 + Math.floor(i / 3) * 80,
  }))
  const byId = Object.fromEntries(positioned.map((n) => [n.id, n]))

  return (
    <div className="widget">
      <div className="widget-head">
        <span>
          <span className="kind">widget</span> · graph subset
        </span>
        <span>{`${nodes.length} nodes · ${edges.length} edges`}</span>
      </div>
      <div className="widget-body">
        <div className="graph">
          {edges.map((e, i) => {
            const a = byId[e.from]
            const b = byId[e.to]
            if (!a || !b) return null
            const dx = b.x - a.x
            const dy = b.y - a.y
            const len = Math.sqrt(dx * dx + dy * dy)
            const ang = (Math.atan2(dy, dx) * 180) / Math.PI
            return (
              <div
                key={i}
                className="gedge"
                style={{
                  left: a.x + 50,
                  top: a.y + 14,
                  width: len,
                  transform: `rotate(${ang}deg)`,
                }}
              />
            )
          })}
          {positioned.map((n) => (
            <div
              key={n.id}
              className={'gnode' + (n.you ? ' you' : '')}
              style={{ left: n.x, top: n.y }}
            >
              {n.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
