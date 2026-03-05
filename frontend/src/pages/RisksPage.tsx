import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { RiskItem, RiskTrends } from '../types/api'

export function RisksPage({ items, focusRiskArea }: { items: RiskItem[]; focusRiskArea?: string | null }) {
  const [trends, setTrends] = useState<RiskTrends | null>(null)

  useEffect(() => {
    ;(async () => {
      try {
        const res = await api.riskTrends()
        setTrends(res)
      } catch {
        setTrends(null)
      }
    })()
  }, [])

  const counts = useMemo(() => ({
    high: items.filter((i) => i.severity === 'high').length,
    med: items.filter((i) => i.severity === 'med').length,
    low: items.filter((i) => i.severity === 'low').length,
    total: Math.max(items.length, 1),
  }), [items])

  const escalated = [...items].sort((a, b) => b.score - a.score).slice(0, 2)

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">risks</h2>
      </div>

      <div className="risk-top-row">
        <div className="severity-panel">
          <div className="section-title" style={{ marginBottom: 10 }}>// severity_distribution</div>
          <SeverityRow label="high" count={counts.high} total={counts.total} color="var(--accent-red)" />
          <SeverityRow label="med" count={counts.med} total={counts.total} color="var(--accent-amber)" />
          <SeverityRow label="low" count={counts.low} total={counts.total} color="var(--accent-green)" />
          {trends && <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>trend snapshot loaded ({trends.has_previous ? 'with previous baseline' : 'first snapshot'})</div>}
        </div>

        <div className="escalated-panel">
          <div className="section-title" style={{ marginBottom: 10, color: 'var(--accent-red)' }}>// recently_escalated</div>
          <div style={{ display: 'grid', gap: 8 }}>
            {escalated.map((r, i) => (
              <div key={`${r.area}-${i}`} className="panel" style={{ padding: 10, borderColor: i === 0 ? 'var(--accent-red)' : 'var(--accent-amber)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{r.area}</span>
                  <strong style={{ color: r.score > 70 ? 'var(--accent-red)' : 'var(--accent-amber)' }}>{r.score}</strong>
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{r.rationale}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="table">
        <div className="table-header" style={{ gridTemplateColumns: '90px 1.1fr 120px 70px 1.3fr' }}>
          <span>severity</span><span>area</span><span>kind</span><span>score</span><span>rationale</span>
        </div>
        {[...items].sort((a, b) => b.score - a.score).map((r, i) => {
          const focused = !!focusRiskArea && r.area === focusRiskArea
          return (
            <div
              key={`${r.area}-${i}`}
              className={`table-row ${focused ? 'selected' : ''}`}
              style={{ gridTemplateColumns: '90px 1.1fr 120px 70px 1.3fr' }}
            >
              <span><span className={`badge badge-${r.severity}`}>{r.severity}</span></span>
              <span>{r.area}</span>
              <span className="muted">{r.kind}</span>
              <span style={{ color: r.score > 70 ? 'var(--accent-red)' : r.score > 40 ? 'var(--accent-amber)' : 'var(--accent-green)' }}>{r.score}</span>
              <span className="muted" style={{ fontSize: 12 }}>{r.rationale}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function SeverityRow({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const pct = Math.round((count / total) * 100)
  return (
    <div className="sev-row">
      <span className="muted" style={{ fontSize: 11 }}>{label}</span>
      <div className="sev-track"><div style={{ width: `${pct}%`, height: '100%', background: color }} /></div>
      <strong style={{ color }}>{count}</strong>
    </div>
  )
}
