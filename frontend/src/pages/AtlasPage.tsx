import type { ChangeItem, DecisionItem, Overview, RiskItem } from '../types/api'

type Props = {
  overview?: Overview
  changes: ChangeItem[]
  risks: RiskItem[]
  decisions: DecisionItem[]
}

export function AtlasPage({ overview, changes, risks, decisions }: Props) {
  const proposed = decisions.filter((d) => d.status === 'proposed').length
  const unresolved = decisions.filter((d) => d.status === 'unresolved').length
  const topRisk = [...risks].sort((a, b) => b.score - a.score)[0]
  const lastChange = changes[0]

  return (
    <section style={{ display: 'grid', gap: 14 }}>
      <div className="page-header">
        <h2 className="page-title">overview</h2>
      </div>

      <div className="kpi-row">
        <Kpi label="// files_indexed" value={overview?.files ?? 0} change="tracked in current project" />
        <Kpi label="// commits_indexed" value={overview?.commits ?? 0} change="latest git timeline" />
        <Kpi label="// modules_mapped" value={overview?.modules ?? 0} change="architecture graph" />
        <Kpi label="// risks_detected" value={overview?.risks ?? 0} change="severity-scored" danger={true} />
        <Kpi
          label="// open_decisions"
          value={decisions.length}
          change={`${proposed} proposed / ${unresolved} unresolved`}
          warn={true}
        />
      </div>

      <div className="narrative-grid">
        <div className="insight-card">
          <div className="insight-title">// what_changed</div>
          <div className="insight-text">
            {lastChange ? `Latest: ${lastChange.sha.slice(0, 7)} — ${lastChange.message}` : 'No recent commits indexed yet.'}
          </div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// why_it_matters</div>
          <div className="insight-text">
            {topRisk ? `Highest risk is ${topRisk.area} (${topRisk.score}) due to ${topRisk.kind}.` : 'Risk model has not produced actionable items yet.'}
          </div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// suggested_action</div>
          <div className="insight-text">
            {proposed > 0 ? `Review ${proposed} proposed decision(s) before next major refactor.` : 'No pending proposals. Validate risk hotspots and schedule refactor windows.'}
          </div>
        </div>
      </div>

      <div className="content-columns">
        <div className="left-column">
          <div className="section-panel">
            <div className="section-header">
              <span className="section-title">// top_changes</span>
            </div>
            {changes.slice(0, 6).map((c) => (
              <div className="row-item" key={c.sha}>
                <span className="commit-sha">{c.sha.slice(0, 7)}</span>
                <span className="commit-msg">{c.message}</span>
                <span className="commit-meta">{c.date?.slice(0, 10) || 'n/a'}</span>
              </div>
            ))}
          </div>

          <div className="section-panel">
            <div className="section-header">
              <span className="section-title">// top_risks</span>
            </div>
            {risks.slice(0, 6).map((r, i) => (
              <div className="row-item" key={`${r.area}-${i}`}>
                <span className={`badge badge-${r.severity}`}>{r.severity}</span>
                <span className="commit-msg">{r.area}</span>
                <span className="commit-meta">{r.score}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="right-column">
          <div className="section-panel">
            <div className="section-header">
              <span className="section-title">// decision_queue</span>
            </div>
            {decisions.slice(0, 8).map((d) => (
              <div className="row-item" key={d.id} style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span className={`status-badge status-${normalizeStatus(d.status)}`}>{d.status}</span>
                  <span className="muted" style={{ fontSize: 11 }}>#dec-{String(d.id).padStart(3, '0')}</span>
                </div>
                <div style={{ fontSize: 12 }}>{d.title}</div>
                <div className="muted" style={{ fontSize: 10 }}>source: {d.source_type || 'manual'}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function Kpi({ label, value, change, danger, warn }: { label: string; value: number; change: string; danger?: boolean; warn?: boolean }) {
  const color = danger ? 'var(--accent-red)' : warn ? 'var(--accent-amber)' : 'var(--text-primary)'
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={{ color }}>{value}</div>
      <div className="kpi-change">{change}</div>
    </div>
  )
}

function normalizeStatus(status: string) {
  if (status === 'accepted') return 'accepted'
  if (status === 'resolved') return 'resolved'
  if (status === 'superseded') return 'superseded'
  if (status === 'unresolved') return 'unresolved'
  return 'proposed'
}
