import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { StoryTimelineItem } from '../types/api'

export function NarrativePage() {
  const [items, setItems] = useState<StoryTimelineItem[]>([])
  const [range, setRange] = useState('30d')

  useEffect(() => {
    api.storyTimeline(range).then((res) => setItems(res.items || [])).catch(() => setItems([]))
  }, [range])

  const narrative = useMemo(() => {
    return items.slice(0, 20).map((s) => {
      const change = s.major_changes?.[0]
      const focus = s.focus_areas?.[0]
      const question = s.open_questions?.[0]
      return {
        id: s.id,
        generated_at: s.generated_at,
        line: change && focus
          ? `To stabilize ${focus.area}, the system introduced/recorded change '${change.message}', affecting intent continuity in this surface.`
          : change
            ? `The project evolved via '${change.message}', shifting operational focus for this snapshot.`
            : focus
              ? `Risk concentration moved toward ${focus.area}, signaling architectural attention needed.`
              : 'Snapshot captured project state without strong causal signals.',
        note: question ? `Open intent question: #dec-${String(question.decision_id).padStart(3, '0')} ${question.title}` : 'No unresolved intent question in this snapshot.',
      }
    })
  }, [items])

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">narrative</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          {['7d', '30d', '90d'].map((r) => (
            <button key={r} className="btn" style={range === r ? { background: 'var(--bg-active)' } : undefined} onClick={() => setRange(r)}>{r}</button>
          ))}
        </div>
      </div>

      <div className="narrative-grid">
        <div className="insight-card">
          <div className="insight-title">// what_changed</div>
          <div className="insight-text">Narrative synthesizes why logic evolved, not only what files changed.</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// why_it_matters</div>
          <div className="insight-text">Developers preserve ownership faster through causal story than raw diff volume.</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// suggested_action</div>
          <div className="insight-text">Review this timeline before approving broad AI-generated refactors.</div>
        </div>
      </div>

      <div className="section-panel">
        <div className="section-header">
          <span className="section-title">// project_story_timeline</span>
          <span className="muted" style={{ fontSize: 11 }}>{items.length} snapshots</span>
        </div>
        <div style={{ maxHeight: '68vh', overflowY: 'auto' }}>
          {narrative.length ? narrative.map((n) => (
            <div key={n.id} className="row-item" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span className="muted" style={{ fontSize: 11 }}>{(n.generated_at || '').replace('T', ' ').slice(0, 19)}</span>
                <span className="badge badge-med">story</span>
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.5 }}>{n.line}</div>
              <div className="muted" style={{ fontSize: 12 }}>{n.note}</div>
            </div>
          )) : <div className="muted" style={{ padding: 12 }}>No story snapshots yet. Run analyze to generate narrative history.</div>}
        </div>
      </div>
    </section>
  )
}
