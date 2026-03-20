import { useEffect, useState } from 'react'
import { api } from '../api/client'

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

        commits.items.forEach(c => combined.push({
          id: c.sha,
          date: c.date,
          type: 'commit',
          title: c.message,
          detail: `commit pulse · ${c.sha.slice(0, 7)}`
        }))

        decisions.items.forEach(d => combined.push({
          id: `dec-${d.id}`,
          date: d.created_at,
          type: 'decision',
          title: `Decision anchor: ${d.title}`,
          detail: d.summary,
          metadata: { status: d.status }
        }))

        story.items.forEach(s => combined.push({
          id: `story-${s.id}`,
          date: s.generated_at,
          type: 'narrative',
          title: 'Narrative shift',
          detail: s.focus_areas?.[0]?.area || 'Logic stabilization'
        }))

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
          <div className="muted" style={{ fontSize: 10, letterSpacing: 2 }}>// project_chronicle</div>
          <h1 style={{ margin: '8px 0 0 0' }}>The Chronicle</h1>
          <div className="muted" style={{ marginTop: 8, maxWidth: 720, fontSize: 13 }}>
            Read the temporal memory of the project. The Chronicle tracks not only what changed, but how the system’s narrative, focus, and tensions evolve over time.
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: 8, background: 'rgba(255,255,255,0.03)', padding: 4, borderRadius: 8 }}>
          <button className={`btn btn-sm ${filter === 'all' ? 'primary' : ''}`} onClick={() => setFilter('all')}>All signals</button>
          <button className={`btn btn-sm ${filter === 'intent' ? 'primary' : ''}`} onClick={() => setFilter('intent')}>Intent only</button>
          <button className={`btn btn-sm ${filter === 'code' ? 'primary' : ''}`} onClick={() => setFilter('code')}>Code only</button>
        </div>
      </header>

      {loading ? (
        <div className="muted">Opening the Chronicle…</div>
      ) : (
        <div className="timeline-trail" style={{ position: 'relative', paddingLeft: 24 }}>
          <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 1, background: 'linear-gradient(to bottom, var(--accent-cyan), transparent)', opacity: 0.3 }} />

          <div style={{ display: 'grid', gap: 40 }}>
            {filteredEvents.map((ev) => (
              <div key={ev.id} className="timeline-item" style={{ position: 'relative' }}>
                <div style={{ 
                  position: 'absolute', left: -28, top: 4, width: 9, height: 9, borderRadius: '50%', 
                  background: ev.type === 'decision' ? 'var(--accent-amber)' : (ev.type === 'narrative' ? 'var(--accent-cyan)' : '#444'),
                  boxShadow: `0 0 10px ${ev.type === 'decision' ? 'var(--accent-amber)' : (ev.type === 'narrative' ? 'var(--accent-cyan)' : 'transparent')}`
                }} />

                <div className="event-content">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span className="muted" style={{ fontSize: 10, fontFamily: 'monospace' }}>{new Date(ev.date).toLocaleString()}</span>
                    <span className="badge badge-low" style={{ fontSize: 9, opacity: 0.6 }}>{labelForType(ev.type)}</span>
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

function labelForType(type: TimelineEvent['type']) {
  if (type === 'commit') return 'commit pulse'
  if (type === 'decision') return 'decision anchor'
  if (type === 'narrative') return 'narrative shift'
  return 'audit event'
}
