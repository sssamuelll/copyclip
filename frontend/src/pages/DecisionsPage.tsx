import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { DecisionHistoryItem, DecisionItem } from '../types/api'

export function DecisionsPage({ items }: { items: DecisionItem[] }) {
  const [selectedId, setSelectedId] = useState<number | null>(items[0]?.id ?? null)
  const [history, setHistory] = useState<DecisionHistoryItem[]>([])

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
    ;(async () => {
      try {
        const res = await api.decisionHistory(selectedId)
        setHistory(res.items || [])
      } catch {
        setHistory([])
      }
    })()
  }, [selectedId])

  const selected = items.find((d) => d.id === selectedId) || null

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
