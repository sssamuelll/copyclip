import { useMemo, useState } from 'react'
import type { ArchEdge, ArchNode } from '../types/api'

export function ArchitecturePage({ nodes, edges }: { nodes: ArchNode[]; edges: ArchEdge[] }) {
  const [selected, setSelected] = useState<string | null>(nodes[0]?.name ?? null)

  const stats = useMemo(() => {
    const map: Record<string, { inbound: number; outbound: number; links: string[] }> = {}
    for (const n of nodes) map[n.name] = { inbound: 0, outbound: 0, links: [] }
    for (const e of edges) {
      if (!map[e.from]) map[e.from] = { inbound: 0, outbound: 0, links: [] }
      if (!map[e.to]) map[e.to] = { inbound: 0, outbound: 0, links: [] }
      map[e.from].outbound += 1
      map[e.from].links.push(`→ ${e.to}`)
      map[e.to].inbound += 1
      map[e.to].links.push(`← ${e.from}`)
    }
    return map
  }, [nodes, edges])

  const current = selected ? stats[selected] : null

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">architecture</h2>
      </div>

      <div className="arch-body">
        <div className="graph-area">
          <div className="section-title" style={{ marginBottom: 10 }}>// module_map</div>
          <div className="graph-grid">
            {nodes.map((n) => {
              const s = stats[n.name] || { inbound: 0, outbound: 0 }
              return (
                <div
                  key={n.name}
                  className={`graph-node ${selected === n.name ? 'active' : ''}`}
                  onClick={() => setSelected(n.name)}
                >
                  <div style={{ fontSize: 13 }}>{n.name}</div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    in {s.inbound} / out {s.outbound}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="side-panel">
          <div className="panel-block">
            <div className="section-title">// selected_module</div>
            <div style={{ marginTop: 8, fontSize: 18, color: 'var(--accent-cyan)' }}>{selected || 'none'}</div>
          </div>

          <div className="panel-block">
            <div className="section-title">// stats</div>
            <div style={{ marginTop: 8, display: 'grid', gap: 6, fontSize: 13 }}>
              <div>inbound deps: <strong>{current?.inbound ?? 0}</strong></div>
              <div>outbound deps: <strong>{current?.outbound ?? 0}</strong></div>
              <div>total edges: <strong>{(current?.inbound ?? 0) + (current?.outbound ?? 0)}</strong></div>
            </div>
          </div>

          <div className="panel-block" style={{ borderBottom: 'none' }}>
            <div className="section-title">// dependencies</div>
            <div style={{ marginTop: 8, display: 'grid', gap: 6 }}>
              {current?.links?.length ? current.links.slice(0, 20).map((l, i) => (
                <div key={`${l}-${i}`} className="muted" style={{ fontSize: 12 }}>{l}</div>
              )) : <div className="muted">No dependency links for selected module.</div>}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
