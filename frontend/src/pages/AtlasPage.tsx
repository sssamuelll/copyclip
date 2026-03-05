import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ChangeItem, DecisionItem, IdentityDriftItem, Overview, RiskItem, StoryTimelineItem } from '../types/api'

type Props = {
  overview?: Overview
  changes: ChangeItem[]
  risks: RiskItem[]
  decisions: DecisionItem[]
}

export function AtlasPage({ overview, changes, risks, decisions }: Props) {
  const [storyItems, setStoryItems] = useState<StoryTimelineItem[]>([])
  const [driftCurrent, setDriftCurrent] = useState<IdentityDriftItem | null>(null)

  useEffect(() => {
    api.storyTimeline('30d').then((res) => setStoryItems(res.items || [])).catch(() => setStoryItems([]))
    api.identityDrift('30d').then((res) => setDriftCurrent(res.current || null)).catch(() => setDriftCurrent(null))
  }, [])

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

      <div className="section-panel">
        <div className="section-header">
          <span className="section-title">// story_timeline_30d</span>
          <span className="muted" style={{ fontSize: 11 }}>{storyItems.length} snapshots</span>
        </div>
        <div style={{ maxHeight: '34vh', overflowY: 'auto' }}>
          {storyItems.length ? storyItems.slice(0, 12).map((s) => (
            <div key={s.id} className="row-item" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span className="muted" style={{ fontSize: 11 }}>{(s.generated_at || '').replace('T', ' ').slice(0, 19)}</span>
                <span className="badge badge-low">focus {s.focus_areas?.length || 0}</span>
                <span className="badge badge-med">changes {s.major_changes?.length || 0}</span>
                <span className="badge badge-high">questions {s.open_questions?.length || 0}</span>
              </div>
              <div style={{ fontSize: 12, marginTop: 6 }}>
                Top focus: {s.focus_areas?.[0]?.area || 'n/a'}
                {s.major_changes?.[0]?.message ? ` · latest change: ${s.major_changes[0].message}` : ''}
              </div>
            </div>
          )) : <div className="muted" style={{ padding: 12 }}>No story snapshots yet. Run analyze to build timeline memory.</div>}
        </div>
      </div>

      <div className="section-panel">
        <div className="section-header">
          <span className="section-title">// identity_drift_30d</span>
          {driftCurrent && (
            <span className={`badge ${driftLevel(driftCurrent) === 'high' ? 'badge-high' : driftLevel(driftCurrent) === 'med' ? 'badge-med' : 'badge-low'}`}>
              {driftLevel(driftCurrent)}
            </span>
          )}
        </div>
        <div style={{ padding: 12, display: 'grid', gap: 10 }}>
          {driftCurrent ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(120px, 1fr))', gap: 10 }}>
                <div className="panel" style={{ padding: 10 }}>
                  <div className="muted" style={{ fontSize: 11 }}>decision_alignment</div>
                  <div style={{ fontSize: 18 }}>{driftCurrent.decision_alignment_score.toFixed(1)}%</div>
                </div>
                <div className="panel" style={{ padding: 10 }}>
                  <div className="muted" style={{ fontSize: 11 }}>architecture_cohesion_delta</div>
                  <div style={{ fontSize: 18 }}>{driftCurrent.architecture_cohesion_delta.toFixed(2)}</div>
                </div>
                <div className="panel" style={{ padding: 10 }}>
                  <div className="muted" style={{ fontSize: 11 }}>risk_concentration</div>
                  <div style={{ fontSize: 18 }}>{driftCurrent.risk_concentration_index.toFixed(1)}%</div>
                </div>
              </div>
              <div>
                <div className="section-title" style={{ marginBottom: 6 }}>// top_causes</div>
                {driftCurrent.causes?.length ? (
                  <div style={{ display: 'grid', gap: 6 }}>
                    {driftCurrent.causes.slice(0, 4).map((c, i) => (
                      <div key={`cause-${i}`} className="muted">• {c}</div>
                    ))}
                  </div>
                ) : (
                  <div className="muted">No major drift causes detected. Current state appears stable.</div>
                )}
              </div>
              <div>
                <div className="section-title" style={{ marginBottom: 6 }}>// stabilization_actions</div>
                <div className="muted">
                  {driftLevel(driftCurrent) === 'high'
                    ? 'Freeze non-critical refactors, resolve proposed decisions, and rebalance top risk hotspots.'
                    : driftLevel(driftCurrent) === 'med'
                      ? 'Prioritize decision closure and reduce dependency hotspots in highest-risk modules.'
                      : 'Keep current direction; validate new AI-generated changes against accepted decisions.'}
                </div>
              </div>
            </>
          ) : (
            <div className="muted">No drift snapshot yet. Run analyze to compute identity drift signals.</div>
          )}
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
                {r.kind === 'intent_drift' && <span className="badge badge-intent">intent</span>}
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

function driftLevel(d: IdentityDriftItem): 'low' | 'med' | 'high' {
  const causes = d.causes?.length || 0
  if (causes >= 2) return 'high'
  if (causes === 1) return 'med'

  // Fallback from score thresholds if causes are missing.
  if (d.decision_alignment_score < 55 || d.risk_concentration_index > 70 || d.architecture_cohesion_delta > 20) return 'high'
  if (d.decision_alignment_score < 70 || d.risk_concentration_index > 55 || d.architecture_cohesion_delta > 14) return 'med'
  return 'low'
}
