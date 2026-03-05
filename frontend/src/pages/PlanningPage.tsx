import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { DecisionItem } from '../types/api'

type Column = 'intentions' | 'aligning' | 'anchored'

interface Task {
  id: string
  title: string
  summary: string
  status: Column
  type: 'manual' | 'agent'
  decisionId?: number
}

export function PlanningPage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadPlanning = async () => {
      try {
        const decisions = await api.decisions()
        
        // Map decisions to Kanban tasks
        const mappedTasks: Task[] = decisions.items.map(d => ({
          id: `task-${d.id}`,
          title: d.title,
          summary: d.summary || '',
          status: d.status === 'accepted' || d.status === 'resolved' ? 'anchored' : 
                  d.status === 'proposed' ? 'intentions' : 'aligning',
          type: (d.source_type as any) || 'manual',
          decisionId: d.id
        }))
        
        setTasks(mappedTasks)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    loadPlanning()
  }, [])

  const renderColumn = (col: Column, label: string) => {
    const colTasks = tasks.filter(t => t.status === col)
    return (
      <div className="kanban-column" style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 300, background: 'rgba(255,255,255,0.01)', borderRadius: 8, padding: 12, border: '1px solid rgba(255,255,255,0.03)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 8px' }}>
          <span className="section-title" style={{ fontSize: 11, letterSpacing: 1 }}>// {label}</span>
          <span className="muted" style={{ fontSize: 10 }}>{colTasks.length}</span>
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {colTasks.map(task => (
            <div key={task.id} className="panel" style={{ padding: 16, cursor: 'pointer', transition: 'transform 0.1s ease', position: 'relative', overflow: 'hidden' }}>
              {task.type === 'agent' && <div style={{ position: 'absolute', top: 0, left: 0, width: 2, height: '100%', background: 'var(--accent-cyan)' }} />}
              
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span className="muted" style={{ fontSize: 9 }}>{task.type === 'agent' ? 'AI Proposal' : 'Human Intent'}</span>
                {task.decisionId && <span className="muted" style={{ fontSize: 9 }}>#dec-{task.decisionId}</span>}
              </div>
              
              <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 500, marginBottom: 6 }}>{task.title}</div>
              <div className="muted" style={{ fontSize: 11, lineHeight: 1.4 }}>{task.summary.slice(0, 100)}{task.summary.length > 100 ? '...' : ''}</div>
            </div>
          ))}
          {colTasks.length === 0 && <div className="muted" style={{ textAlign: 'center', padding: 40, fontSize: 11, border: '1px dashed #222', borderRadius: 6 }}>No intent anchored here.</div>}
        </div>
      </div>
    )
  }

  return (
    <div className="page-container">
      <header style={{ marginBottom: 32 }}>
        <div className="muted" style={{ fontSize: 10, letterSpacing: 2 }}>// strategy_board_v1</div>
        <h1 style={{ margin: '8px 0 0 0' }}>Planning & Intentions</h1>
      </header>

      {loading ? (
        <div className="muted">Synchronizing intent board...</div>
      ) : (
        <div className="kanban-board" style={{ display: 'flex', gap: 24, overflowX: 'auto', paddingBottom: 24 }}>
          {renderColumn('intentions', 'BACKLOG_OF_INTENT')}
          {renderColumn('aligning', 'ACTIVE_ALIGNMENT')}
          {renderColumn('anchored', 'ANCHORED_IN_CODE')}
        </div>
      )}
    </div>
  )
}
