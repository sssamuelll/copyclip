import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ChangeItem, DecisionItem, Overview, RiskItem, HeatmapItem } from '../types/api'

type Props = {
  overview?: Overview
  changes: ChangeItem[]
  risks: RiskItem[]
  decisions: DecisionItem[]
}

export function AtlasPage({ overview, changes, risks, decisions }: Props) {
  const [heatmap, setHeatmap] = useState<HeatmapItem[]>([])

  useEffect(() => {
    api.heatmap().then(res => {
      // Sort by score to see top debt
      const sorted = res.items.sort((a, b) => b.score - a.score)
      setHeatmap(sorted)
    })
  }, [])

  return (
    <section>
      <h2>project atlas</h2>
      
      {/* Narrative Section */}
      <div className="panel" style={{ marginTop: '1rem', borderLeft: '4px solid var(--accent)' }}>
        <h3>Story</h3>
        <div style={{ marginTop: '0.5rem', lineHeight: '1.6', opacity: 0.9, whiteSpace: 'pre-wrap' }}>
          {overview?.story || 'No narrative story generated yet. Run analysis to build the project story.'}
        </div>
      </div>

      <div className="kpis" style={{ marginTop: '1.5rem' }}>
        <Card label="files" value={overview?.files ?? 0} />
        <Card label="commits" value={overview?.commits ?? 0} />
        <Card label="modules" value={overview?.modules ?? 0} />
        <Card label="risks" value={overview?.risks ?? 0} />
        <Card label="issues" value={overview?.issues ?? 0} />
      </div>

      {/* Heatmap Section */}
      <div className="panel" style={{ marginTop: '1.5rem' }}>
        <h3>Technical Debt Heatmap</h3>
        <p className="muted" style={{ fontSize: '0.8rem', marginBottom: '1rem' }}>
          Files sized by disk space, colored by Debt Score (Complexity × Churn). Red = Urgent Refactor.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
          {heatmap.slice(0, 50).map(item => {
            const size = Math.max(40, Math.min(150, (item.size / 1024) * 2))
            const color = item.score > 60 ? '#7f1d1d' : (item.score > 30 ? '#92400e' : '#064e3b')
            return (
              <div 
                key={item.path} 
                title={`${item.path}\nScore: ${item.score}\nSize: ${Math.round(item.size/1024)}KB`}
                style={{
                  width: size,
                  height: size,
                  background: color,
                  border: '1px solid rgba(255,255,255,0.1)',
                  padding: '4px',
                  fontSize: '0.6rem',
                  overflow: 'hidden',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  textAlign: 'center',
                  cursor: 'help'
                }}
              >
                {item.path.split('/').pop()}
              </div>
            )
          })}
        </div>
      </div>

      <div className="cols" style={{ marginTop: '1.5rem' }}>
        <Panel title="recent changes" items={changes.slice(0, 8).map((c) => `${c.sha.slice(0, 7)} — ${c.message}`)} />
        <Panel title="top risks" items={risks.slice(0, 8).map((r) => `[${r.severity}] ${r.area} (${r.score})`)} />
        <Panel title="open decisions" items={decisions.slice(0, 8).map((d) => `#${d.id} [${d.status}] ${d.title}`)} />
      </div>
    </section>
  )
}

function Card({ label, value }: { label: string; value: number }) {
  return (
    <div className="card">
      <div className="muted">{label}</div>
      <div className="value">{value}</div>
    </div>
  )
}

function Panel({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      <ul>{items.length ? items.map((i) => <li key={i}>{i}</li>) : <li className="muted">No data</li>}</ul>
    </div>
  )
}
