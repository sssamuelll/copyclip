import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { DecisionHistoryItem, DecisionItem } from '../types/api'

export function DecisionsPage({ items }: { items: DecisionItem[] }) {
  const [selectedId, setSelectedId] = useState<number | null>(items[0]?.id ?? null)
  const [history, setHistory] = useState<DecisionHistoryItem[]>([])
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const selected = items.find((d) => d.id === selectedId) || null

  const loadHistory = async (id: number) => {
    try {
      const res = await api.decisionHistory(id)
      setHistory(res.items || [])
    } catch {
      setHistory([])
    }
  }

  useEffect(() => {
    if (!items.length) {
      setSelectedId(null)
      setHistory([])
      return
    }
    if (!selectedId || !items.find((d) => d.id === selectedId)) {
      setSelectedId(items[0].id)
    }
  }, [items, selectedId])

  useEffect(() => {
    if (!selectedId) return
    loadHistory(selectedId)
  }, [selectedId])

  const onTransition = async (status: string) => {
    if (!selected) return
    setError('')
    try {
      await api.updateDecisionStatus(selected.id, status, note)
      await loadHistory(selected.id)
    } catch (e: any) {
      setError(e?.message || 'Status update failed')
    }
  }

  const onAddRef = async () => {
    if (!selected) return
    setError('')
    const refType = (prompt('Ref type (file|commit|doc)', 'file') || 'file') as 'file' | 'commit' | 'doc'
    const refValue = (prompt('Ref value') || '').trim()
    if (!refValue) return
    try {
      await api.addDecisionRef(selected.id, refType, refValue)
      await loadHistory(selected.id)
    } catch (e: any) {
      setError(e?.message || 'Add ref failed')
    }
  }

  return (
    <section>
      <h2>decisions</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>decision list</h3>
          <ul>
            {items.map((d) => (
              <li
                key={d.id}
                onClick={() => setSelectedId(d.id)}
                style={{ cursor: 'pointer', color: d.id === selectedId ? '#10b981' : undefined }}
              >
                #{d.id} [{d.status}] {d.title}
              </li>
            ))}
          </ul>
        </div>

        <div className="panel">
          <h3 style={{ marginTop: 0 }}>decision detail</h3>
          {selected ? (
            <>
              <div><strong>#{selected.id}</strong> — {selected.title}</div>
              <div className="muted">status: {selected.status} | source: {selected.source_type || 'manual'}</div>
              <p>{selected.summary || 'No summary.'}</p>

              <div style={{ display: 'grid', gap: 8, marginBottom: 10 }}>
                <textarea
                  rows={2}
                  placeholder="Optional evidence note (required if resolving without refs)"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button onClick={() => onTransition('accepted')}>Accept</button>
                  <button onClick={() => onTransition('resolved')}>Resolve</button>
                  <button onClick={() => onTransition('superseded')}>Supersede</button>
                  <button onClick={onAddRef}>Add Ref</button>
                </div>
                {error && <div className="error">{error}</div>}
              </div>

              <h4 style={{ marginBottom: 8 }}>timeline</h4>
              <ul>
                {history.length ? (
                  history.map((h) => (
                    <li key={h.id}>
                      [{h.created_at?.slice(0, 19)}] {h.action}
                      {h.from_status || h.to_status ? ` (${h.from_status || '-'} → ${h.to_status || '-'})` : ''}
                      {h.note ? ` — ${h.note}` : ''}
                    </li>
                  ))
                ) : (
                  <li className="muted">No timeline events yet.</li>
                )}
              </ul>
            </>
          ) : (
            <div className="muted">No decisions yet.</div>
          )}
        </div>
      </div>
    </section>
  )
}
