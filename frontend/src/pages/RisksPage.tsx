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

  const sortedByScore = [...items].sort((a, b) => b.score - a.score)
  const escalated = sortedByScore.slice(0, 2)
  const top = sortedByScore[0]
  const intentDriftCount = items.filter((i) => i.kind === 'intent_drift').length

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">Distortion Field</h2>
      </div>

      <div className="narrative-grid">
        <div className="insight-card">
          <div className="insight-title">// field_state</div>
          <div className="insight-text">{trends?.has_previous ? 'The field has a previous baseline. Distortions can now be read against prior state.' : 'This appears to be an early reading of the field.'}</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// highest_distortion</div>
          <div className="insight-text">{top ? `${top.area} currently carries the strongest distortion signal (${top.score}).` : 'No active distortion signals detected.'}</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// suggested_action</div>
          <div className="insight-text">
            Prioritize the top three distortions, then link each one to a mitigation owner or an anchored decision.
            {intentDriftCount > 0 ? ` ${intentDriftCount} intent-drift signal(s) need immediate oracle review.` : ''}
          </div>
        </div>
      </div>

      <div className="risk-top-row">
        <div className="severity-panel">
          <div className="section-title" style={{ marginBottom: 10 }}>// turbulence_distribution</div>
          <SeverityRow label="high distortion" count={counts.high} total={counts.total} color="var(--accent-red)" />
          <SeverityRow label="medium distortion" count={counts.med} total={counts.total} color="var(--accent-amber)" />
          <SeverityRow label="low distortion" count={counts.low} total={counts.total} color="var(--accent-green)" />
          {trends && <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>trend snapshot loaded ({trends.has_previous ? 'with previous baseline' : 'first snapshot'})</div>}
        </div>

        <div className="escalated-panel">
          <div className="section-title" style={{ marginBottom: 10, color: 'var(--accent-red)' }}>// active_turbulence</div>
          <div style={{ display: 'grid', gap: 8 }}>
            {escalated.map((r, i) => (
              <div key={`${r.area}-${i}`} className="panel" style={{ padding: 10, borderColor: i === 0 ? 'var(--accent-red)' : 'var(--accent-amber)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                  <span>{r.area}</span>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    {r.kind === 'intent_drift' && <span className="badge badge-intent">intent</span>}
                    <strong style={{ color: r.score > 70 ? 'var(--accent-red)' : 'var(--accent-amber)' }}>{r.score}</strong>
                  </div>
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{r.rationale}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="table">
        <div className="table-header" style={{ gridTemplateColumns: '110px 1.1fr 120px 70px 1.3fr' }}>
          <span>severity</span><span>area</span><span>kind</span><span>score</span><span>rationale</span>
        </div>
        {sortedByScore.map((r, i) => {
          const focused = !!focusRiskArea && r.area === focusRiskArea
          return (
            <div
              key={`${r.area}-${i}`}
              className={`table-row ${focused ? 'selected' : ''}`}
              style={{ gridTemplateColumns: '110px 1.1fr 120px 70px 1.3fr' }}
            >
              <span><span className={`badge badge-${r.severity}`}>{severityLabel(r.severity)}</span></span>
              <span>{r.area}</span>
              <span>{r.kind === 'intent_drift' ? <span className="badge badge-intent">intent_drift</span> : <span className="muted">{r.kind}</span>}</span>
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

function severityLabel(severity: string) {
  if (severity === 'high') return 'high turbulence'
  if (severity === 'med') return 'medium'
  return 'low'
}
