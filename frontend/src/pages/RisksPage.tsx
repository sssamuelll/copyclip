import { useEffect, useState } from 'react'
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

  return (
    <section>
      <h2>risks</h2>

      <div className="panel" style={{ marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>risk trend</h3>
        {!trends ? (
          <div className="muted">No trend data yet.</div>
        ) : (
          <ul>
            {Object.keys(trends.latest).length === 0 ? (
              <li className="muted">No risk breakdown in snapshots yet.</li>
            ) : (
              Object.entries(trends.latest).map(([kind, count]) => {
                const d = trends.delta?.[kind] ?? 0
                const sign = d > 0 ? '+' : ''
                return (
                  <li key={kind}>
                    {kind}: {count} ({sign}{d} vs previous)
                  </li>
                )
              })
            )}
          </ul>
        )}
      </div>

      <div className="panel">
        <ul>{items.map((r, i) => {
          const focused = !!focusRiskArea && r.area === focusRiskArea
          return <li key={i} style={focused ? { background: 'rgba(16,185,129,0.2)', padding: '2px 4px' } : undefined}>[{r.severity}] {r.area} — {r.rationale} ({r.score})</li>
        })}</ul>
      </div>
    </section>
  )
}
