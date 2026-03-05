import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { DecisionHistoryItem, DecisionItem, DecisionLinkItem } from '../types/api'

export function DecisionsPage({ items, focusDecisionId }: { items: DecisionItem[]; focusDecisionId?: number | null }) {
  const [selectedId, setSelectedId] = useState<number | null>(items[0]?.id ?? null)
  const [history, setHistory] = useState<DecisionHistoryItem[]>([])
  const [links, setLinks] = useState<DecisionLinkItem[]>([])
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [tab, setTab] = useState<'all' | 'proposed' | 'accepted' | 'resolved' | 'superseded'>('all')
  const [linkType, setLinkType] = useState<'file_glob' | 'module'>('file_glob')
  const [targetPattern, setTargetPattern] = useState('')

  const filtered = useMemo(() => (tab === 'all' ? items : items.filter((d) => d.status === tab)), [items, tab])
  const selected = filtered.find((d) => d.id === selectedId) || items.find((d) => d.id === selectedId) || null

  const loadHistory = async (id: number) => {
    try {
      const res = await api.decisionHistory(id)
      setHistory(res.items || [])
    } catch {
      setHistory([])
    }
  }

  const loadLinks = async (id: number) => {
    try {
      const res = await api.decisionLinks(id)
      setLinks(res.items || [])
    } catch {
      setLinks([])
    }
  }

  useEffect(() => {
    if (!filtered.length) {
      setSelectedId(items[0]?.id ?? null)
      return
    }
    if (!selectedId || !filtered.find((d) => d.id === selectedId)) setSelectedId(filtered[0].id)
  }, [filtered, items, selectedId])

  useEffect(() => {
    if (selectedId) {
      loadHistory(selectedId)
      loadLinks(selectedId)
    }
  }, [selectedId])

  useEffect(() => {
    if (focusDecisionId && items.find((d) => d.id === focusDecisionId)) setSelectedId(focusDecisionId)
  }, [focusDecisionId, items])

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

  const addLink = async () => {
    if (!selected || !targetPattern.trim()) return
    setError('')
    try {
      await api.addDecisionLink(selected.id, linkType, targetPattern.trim())
      setTargetPattern('')
      await loadLinks(selected.id)
      await loadHistory(selected.id)
    } catch (e: any) {
      setError(e?.message || 'Adding decision link failed')
    }
  }

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">decisions</h2>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {(['all', 'proposed', 'accepted', 'resolved', 'superseded'] as const).map((s) => (
          <button key={s} className="btn" style={tab === s ? { background: 'var(--bg-active)' } : undefined} onClick={() => setTab(s)}>
            {s} {s !== 'all' ? `(${items.filter((d) => d.status === s).length})` : `(${items.length})`}
          </button>
        ))}
      </div>

      <div className="split">
        <div className="table">
          <div className="table-header">
            <span>id</span><span>title</span><span>status</span><span>source</span>
          </div>
          {filtered.map((d) => (
            <div key={d.id} className={`table-row ${d.id === selectedId ? 'selected' : ''}`} onClick={() => setSelectedId(d.id)}>
              <span>#dec-{String(d.id).padStart(3, '0')}</span>
              <span>{d.title}</span>
              <span><span className={`status-badge status-${normalizeStatus(d.status)}`}>{d.status}</span></span>
              <span className="muted">{d.source_type || 'manual'}</span>
            </div>
          ))}
        </div>

        <div className="detail-panel">
          {selected ? (
            <>
              <div className="detail-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <strong>#dec-{String(selected.id).padStart(3, '0')}</strong>
                  <span className={`status-badge status-${normalizeStatus(selected.status)}`}>{selected.status}</span>
                </div>
                <div style={{ marginTop: 8 }}>{selected.title}</div>
                <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>created: {selected.created_at?.slice(0, 19) || 'n/a'} | source: {selected.source_type || 'manual'}</div>
              </div>

              <div className="detail-body">
                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>summary</div>
                  <div style={{ fontSize: 13 }}>{selected.summary || 'No summary.'}</div>
                </div>

                <textarea
                  rows={2}
                  placeholder="Optional evidence note (required if resolving without refs)"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  style={{ background: 'var(--bg)', color: 'var(--text-primary)', border: '1px solid var(--border)', padding: 8 }}
                />

                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button className="btn primary" onClick={() => onTransition('accepted')}>accept</button>
                  <button className="btn" onClick={() => onTransition('resolved')}>resolve</button>
                  <button className="btn" onClick={() => onTransition('superseded')}>supersede</button>
                </div>

                <div className="panel" style={{ padding: 10 }}>
                  <div className="section-title" style={{ marginBottom: 6 }}>// intent_links (decision ↔ code)</div>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                    <select value={linkType} onChange={(e) => setLinkType(e.target.value as any)} style={{ background: 'var(--bg)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}>
                      <option value="file_glob">file_glob</option>
                      <option value="module">module</option>
                    </select>
                    <input
                      value={targetPattern}
                      onChange={(e) => setTargetPattern(e.target.value)}
                      placeholder={linkType === 'file_glob' ? 'frontend/src/**/*.ts' : 'module_name'}
                      style={{ flex: 1, background: 'var(--bg)', color: 'var(--text-primary)', border: '1px solid var(--border)', padding: 8 }}
                    />
                    <button className="btn" onClick={addLink}>link</button>
                  </div>
                  <div style={{ display: 'grid', gap: 6 }}>
                    {links.length ? links.map((l) => (
                      <div key={l.id} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: 12 }}>{l.link_type}: {l.target_pattern}</span>
                        <span className="muted" style={{ fontSize: 11 }}>{l.created_at?.slice(0, 19) || 'n/a'}</span>
                      </div>
                    )) : <div className="muted">No intent links yet.</div>}
                  </div>
                </div>

                {error && <div className="error">{error}</div>}

                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>timeline</div>
                  <div style={{ display: 'grid', gap: 8 }}>
                    {history.length ? history.map((h) => (
                      <div key={h.id} className="panel" style={{ padding: 8, fontSize: 12 }}>
                        [{h.created_at?.slice(0, 19)}] {h.action}
                        {h.from_status || h.to_status ? ` (${h.from_status || '-'} → ${h.to_status || '-'})` : ''}
                        {h.note ? ` — ${h.note}` : ''}
                      </div>
                    )) : <div className="muted">No timeline events yet.</div>}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="detail-body muted">No decisions yet.</div>
          )}
        </div>
      </div>
    </section>
  )
}

function normalizeStatus(status: string) {
  if (status === 'accepted') return 'accepted'
  if (status === 'resolved') return 'resolved'
  if (status === 'superseded') return 'superseded'
  if (status === 'unresolved') return 'unresolved'
  return 'proposed'
}
