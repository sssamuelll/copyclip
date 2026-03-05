import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { ArchEdge, ArchNode, CognitiveLoadItem } from '../types/api'

export function ArchitecturePage({ nodes, edges }: { nodes: ArchNode[]; edges: ArchEdge[] }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [showFog, setShowFog] = useState(false)
  const [fogMap, setFogMap] = useState<Record<string, CognitiveLoadItem>>({})

  useEffect(() => {
    api.cognitiveLoad()
      .then((res) => {
        const m: Record<string, CognitiveLoadItem> = {}
        for (const item of res.items || []) m[item.module] = item
        setFogMap(m)
      })
      .catch(() => setFogMap({}))
  }, [])

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

  useEffect(() => {
    if (!nodes.length) {
      setSelected(null)
      return
    }

    const ranked = [...nodes]
      .map((n) => ({ name: n.name, degree: (stats[n.name]?.inbound || 0) + (stats[n.name]?.outbound || 0) }))
      .sort((a, b) => b.degree - a.degree)

    const best = ranked.find((r) => !r.name.startsWith('.') && r.name !== 'root') || ranked[0]
    if (!selected || !stats[selected]) setSelected(best?.name || null)
  }, [nodes, stats, selected])

  const current = selected ? stats[selected] : null
  const currentFog = selected ? fogMap[selected] : undefined

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">architecture</h2>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
          <input type="checkbox" checked={showFog} onChange={(e) => setShowFog(e.target.checked)} />
          fog of war (color by cognitive debt)
        </label>
      </div>

      <div className="arch-body">
        <div className="graph-area">
          <div className="section-title" style={{ marginBottom: 10 }}>// module_map</div>
          <div className="graph-grid">
            {nodes.map((n) => {
              const s = stats[n.name] || { inbound: 0, outbound: 0 }
              const fog = fogMap[n.name]
              const fogLevel = fog?.fog_level || 'low'
              const fogStyle = showFog
                ? fogLevel === 'high'
                  ? { borderColor: 'var(--accent-red)', background: 'rgba(239,68,68,.17)' }
                  : fogLevel === 'med'
                    ? { borderColor: 'var(--accent-amber)', background: 'rgba(245,158,11,.16)' }
                    : { borderColor: 'var(--accent-green)', background: 'rgba(16,185,129,.12)' }
                : undefined

              return (
                <div
                  key={n.name}
                  className={`graph-node ${selected === n.name ? 'active' : ''}`}
                  style={fogStyle}
                  onClick={() => setSelected(n.name)}
                >
                  <div style={{ fontSize: 13 }}>{n.name}</div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    in {s.inbound} / out {s.outbound}
                    {showFog && fog ? ` · debt ${fog.cognitive_debt_score.toFixed(1)}` : ''}
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
              <div>cognitive debt: <strong>{currentFog ? currentFog.cognitive_debt_score.toFixed(1) : 'n/a'}</strong></div>
              <div>fog level: <strong>{currentFog?.fog_level || 'n/a'}</strong></div>
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
