import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ChangeItem, DecisionItem, StoryTimelineItem } from '../types/api'

type TimelineEvent = {
  id: string
  date: string
  type: 'commit' | 'decision' | 'narrative' | 'audit'
  title: string
  detail?: string
  author?: string
  metadata?: any
}

export function TimelinePage() {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'intent' | 'code'>('all')

  useEffect(() => {
    const loadTimeline = async () => {
      try {
        const [commits, decisions, story] = await Promise.all([
          api.changes(),
          api.decisions(),
          api.storyTimeline('30d')
        ])

        const combined: TimelineEvent[] = []

        // 1. Add Commits
        commits.items.forEach(c => combined.push({
          id: c.sha,
          date: c.date,
          type: 'commit',
          title: c.message,
          detail: `sha: ${c.sha.slice(0, 7)}`
        }))

        // 2. Add Decisions
        decisions.items.forEach(d => combined.push({
          id: `dec-${d.id}`,
          date: d.created_at,
          type: 'decision',
          title: `Decision: ${d.title}`,
          detail: d.summary,
          metadata: { status: d.status }
        }))

        // 3. Add Narrative Snapshots
        story.items.forEach(s => combined.push({
          id: `story-${s.id}`,
          date: s.generated_at,
          type: 'narrative',
          title: 'Project Focus Shift',
          detail: s.focus_areas?.[0]?.area || 'Logic stabilization'
        }))

        // Sort descending
        combined.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
        setEvents(combined)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }

    loadTimeline()
  }, [])

  const filteredEvents = events.filter(e => {
    if (filter === 'intent') return e.type === 'decision' || e.type === 'narrative'
    if (filter === 'code') return e.type === 'commit'
    return true
  })

  return (
    <div className="page-container" style={{ paddingBottom: 60 }}>
      <header style={{ marginBottom: 32, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div className="muted" style={{ fontSize: 10, letterSpacing: 2 }}>// project_chronicle_v1</div>
          <h1 style={{ margin: '8px 0 0 0' }}>Event Timeline</h1>
        </div>
        
        <div style={{ display: 'flex', gap: 8, background: 'rgba(255,255,255,0.03)', padding: 4, borderRadius: 8 }}>
          <button className={`btn btn-sm ${filter === 'all' ? 'primary' : ''}`} onClick={() => setFilter('all')}>All Events</button>
          <button className={`btn btn-sm ${filter === 'intent' ? 'primary' : ''}`} onClick={() => setFilter('intent')}>Intent Only</button>
          <button className={`btn btn-sm ${filter === 'code' ? 'primary' : ''}`} onClick={() => setFilter('code')}>Code Only</button>
        </div>
      </header>

      {loading ? (
        <div className="muted">Scanning temporal buffers...</div>
      ) : (
        <div className="timeline-trail" style={{ position: 'relative', paddingLeft: 24 }}>
          {/* Vertical Line */}
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 1, background: 'linear-gradient(to bottom, var(--accent-cyan), transparent)', opacity: 0.3 }} />

          <div style={{ display: 'grid', gap: 40 }}>
            {filteredEvents.map((ev) => (
              <div key={ev.id} className="timeline-item" style={{ position: 'relative' }}>
                {/* Node Dot */}
                <div style={{ 
                  position: 'absolute', left: -28, top: 4, width: 9, height: 9, borderRadius: '50%', 
                  background: ev.type === 'decision' ? 'var(--accent-amber)' : (ev.type === 'narrative' ? 'var(--accent-cyan)' : '#444'),
                  boxShadow: `0 0 10px ${ev.type === 'decision' ? 'var(--accent-amber)' : (ev.type === 'narrative' ? 'var(--accent-cyan)' : 'transparent')}`
                }} />

                <div className="event-content">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span className="muted" style={{ fontSize: 10, fontFamily: 'monospace' }}>{new Date(ev.date).toLocaleString()}</span>
                    <span className="badge badge-low" style={{ fontSize: 9, opacity: 0.6 }}>{ev.type}</span>
                  </div>
                  
                  <div style={{ fontSize: 15, color: 'var(--text-primary)', fontWeight: 500 }}>{ev.title}</div>
                  {ev.detail && <div className="muted" style={{ fontSize: 12, marginTop: 6, lineHeight: 1.5 }}>{ev.detail}</div>}
                  
                  {ev.author && (
                    <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div style={{ width: 16, height: 16, borderRadius: '50%', background: '#333', fontSize: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {ev.author[0].toUpperCase()}
                      </div>
                      <span className="muted" style={{ fontSize: 10 }}>{ev.author}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
