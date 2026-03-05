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
    const ordered = [...items].sort((a, b) => new Date(b.generated_at).getTime() - new Date(a.generated_at).getTime())

    return ordered.slice(0, 20).map((s, idx) => {
      const prev = ordered[idx + 1]
      const currFocus = s.focus_areas?.[0]?.area || null
      const prevFocus = prev?.focus_areas?.[0]?.area || null
      const currQ = s.open_questions?.length || 0
      const prevQ = prev?.open_questions?.length || 0
      const currChange = s.major_changes?.[0]?.message || null

      let deltaLine = 'Intent continuity remained stable between snapshots.'
      if (currFocus && prevFocus && currFocus !== prevFocus) {
        deltaLine = `Intent focus shifted from ${prevFocus} to ${currFocus}.`
      } else if (currQ > prevQ) {
        deltaLine = `Intent ambiguity increased (${prevQ} → ${currQ} open decision questions).`
      } else if (currQ < prevQ) {
        deltaLine = `Intent ambiguity decreased (${prevQ} → ${currQ}); decision clarity improved.`
      } else if (currChange) {
        deltaLine = `Latest structural move: '${currChange}'.`
      }

      const causal = currFocus
        ? `To preserve intent around ${currFocus}, current evolution should be validated against linked decisions before merge.`
        : 'No dominant focus area; review top risks and accepted decisions for alignment.'

      return {
        id: s.id,
        generated_at: s.generated_at,
        deltaLine,
        causal,
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
          <div className="insight-text">Narrative now compares each snapshot against the previous one.</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// why_it_matters</div>
          <div className="insight-text">This highlights intention delta, not only file-level movement.</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// suggested_action</div>
          <div className="insight-text">Use this view before approving AI-heavy refactors or handoffs.</div>
        </div>
      </div>

      <div className="section-panel">
        <div className="section-header">
          <span className="section-title">// intention_delta_timeline</span>
          <span className="muted" style={{ fontSize: 11 }}>{items.length} snapshots</span>
        </div>
        <div style={{ maxHeight: '68vh', overflowY: 'auto' }}>
          {narrative.length ? narrative.map((n) => (
            <div key={n.id} className="row-item" style={{ flexDirection: 'column', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span className="muted" style={{ fontSize: 11 }}>{(n.generated_at || '').replace('T', ' ').slice(0, 19)}</span>
                <span className="badge badge-med">delta</span>
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.5 }}>{n.deltaLine}</div>
              <div className="muted" style={{ fontSize: 12 }}>{n.causal}</div>
            </div>
          )) : <div className="muted" style={{ padding: 12 }}>No story snapshots yet. Run analyze to generate narrative history.</div>}
        </div>
      </div>
    </section>
  )
}
