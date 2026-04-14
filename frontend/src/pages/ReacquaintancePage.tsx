import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { ReacquaintanceEvidenceItem, ReacquaintanceResponse } from '../types/api'

type Props = {
  onOpenDecision?: (id: number) => void
  onOpenRisk?: (area: string) => void
  onOpenChanges?: (opts?: { commitId?: string | null; filePath?: string | null }) => void
}

const BASELINE_OPTIONS = [
  { value: 'last_seen', label: 'since last visit' },
  { value: 'last_analysis', label: 'since last analysis' },
  { value: 'window', label: 'rolling window' },
  { value: 'checkpoint', label: 'named checkpoint' },
] as const

export function ReacquaintancePage({ onOpenDecision, onOpenRisk, onOpenChanges }: Props) {
  const [mode, setMode] = useState('last_seen')
  const [windowValue, setWindowValue] = useState('7d')
  const [checkpoint, setCheckpoint] = useState('')
  const [data, setData] = useState<ReacquaintanceResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.reacquaintance({
        mode,
        window: mode === 'window' ? windowValue : undefined,
        checkpoint: mode === 'checkpoint' && checkpoint.trim() ? checkpoint.trim() : undefined,
      })
      setData(res)
    } catch (e) {
      setData(null)
      setError(e instanceof Error ? e.message : 'Failed to load reacquaintance briefing')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const evidenceMap = useMemo(() => {
    const map = new Map<string, ReacquaintanceEvidenceItem>()
    ;(data?.evidence_index || []).forEach((item) => map.set(item.id, item))
    return map
  }, [data])

  const openEvidence = (evidenceId: string) => {
    const item = evidenceMap.get(evidenceId)
    if (!item) return
    if (item.type === 'decision') {
      const raw = item.ref.replace(/^#?/, '')
      const id = Number(raw)
      if (!Number.isNaN(id)) onOpenDecision?.(id)
      return
    }
    if (item.type === 'risk') {
      onOpenRisk?.(item.ref)
      return
    }
    if (item.type === 'commit') {
      onOpenChanges?.({ commitId: item.ref })
      return
    }
    if (item.type === 'file') {
      onOpenChanges?.({ filePath: item.ref })
      return
    }
  }

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">reacquaintance</h2>
      </div>

      <div className="section-panel">
        <div className="section-header">
          <span className="section-title">// catch_me_up</span>
        </div>
        <div style={{ padding: 12, display: 'grid', gap: 12 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              {BASELINE_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
            </select>
            {mode === 'window' && (
              <input value={windowValue} onChange={(e) => setWindowValue(e.target.value)} placeholder="7d" />
            )}
            {mode === 'checkpoint' && (
              <input value={checkpoint} onChange={(e) => setCheckpoint(e.target.value)} placeholder="checkpoint name" />
            )}
            <button className="btn" onClick={load} disabled={loading}>{loading ? 'loading…' : 'refresh'}</button>
          </div>

          {error && <div className="error">{error}</div>}

          {data && (
            <>
              <div className="narrative-grid">
                <InfoCard title="// baseline" text={data.meta?.baseline_label || mode} />
                <InfoCard title="// confidence" text={String(data.meta?.confidence || 'low')} />
                <InfoCard title="// generated_at" text={data.meta?.generated_at?.replace('T', ' ').slice(0, 16) || 'n/a'} />
              </div>

              <div className="insight-card">
                <div className="insight-title">// project_refresher</div>
                <div className="insight-text">{data.project_refresher?.summary}</div>
                <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>{data.project_refresher?.why_now}</div>
                <EvidenceChips ids={data.project_refresher?.evidence || []} evidenceMap={evidenceMap} onOpen={openEvidence} />
              </div>

              <div className="split" style={{ gridTemplateColumns: '1.3fr 1fr' }}>
                <div className="panel" style={{ padding: 12 }}>
                  <div className="section-title" style={{ marginBottom: 8 }}>// top_changes</div>
                  <div style={{ display: 'grid', gap: 10 }}>
                    {data.top_changes?.length ? data.top_changes.map((item, idx) => (
                      <div key={`${item.title}-${idx}`} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
                        <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center' }}>
                          <strong>{item.title}</strong>
                          <span className="badge badge-high" style={{ marginLeft: 'auto' }}>{Math.round(item.importance)}</span>
                        </div>
                        <div className="muted" style={{ fontSize: 12 }}>{item.summary}</div>
                        <div className="muted" style={{ fontSize: 11 }}>area: {item.primary_area}</div>
                        <EvidenceChips ids={item.evidence} evidenceMap={evidenceMap} onOpen={openEvidence} />
                      </div>
                    )) : <div className="muted">No top changes surfaced for this baseline.</div>}
                  </div>
                </div>

                <div className="panel" style={{ padding: 12 }}>
                  <div className="section-title" style={{ marginBottom: 8 }}>// read_first</div>
                  <div style={{ display: 'grid', gap: 10 }}>
                    {data.read_first?.length ? data.read_first.map((item) => (
                      <div key={`${item.rank}-${item.target}`} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
                        <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center' }}>
                          <span className="badge badge-low">#{item.rank}</span>
                          <strong>{item.target}</strong>
                          <button className="btn" style={{ marginLeft: 'auto' }} onClick={() => onOpenChanges?.({ filePath: item.target })}>inspect</button>
                        </div>
                        <div className="muted" style={{ fontSize: 12 }}>{item.reason}</div>
                        <div className="muted" style={{ fontSize: 11 }}>{item.expected_payoff} · ~{item.estimated_minutes} min</div>
                        <EvidenceChips ids={item.evidence} evidenceMap={evidenceMap} onOpen={openEvidence} />
                      </div>
                    )) : <div className="muted">No prioritized reading sequence available yet.</div>}
                  </div>
                </div>
              </div>

              <div className="split" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <div className="panel" style={{ padding: 12 }}>
                  <div className="section-title" style={{ marginBottom: 8 }}>// relevant_decisions</div>
                  <div style={{ display: 'grid', gap: 10 }}>
                    {data.relevant_decisions?.length ? data.relevant_decisions.map((item) => (
                      <div key={item.id} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
                        <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center' }}>
                          <span className="status-badge status-proposed">{item.status}</span>
                          <strong>{item.title}</strong>
                          <button className="btn" style={{ marginLeft: 'auto' }} onClick={() => onOpenDecision?.(item.id)}>open</button>
                        </div>
                        <div className="muted" style={{ fontSize: 12 }}>{item.why_now}</div>
                        <EvidenceChips ids={item.evidence} evidenceMap={evidenceMap} onOpen={openEvidence} />
                      </div>
                    )) : <div className="muted">No relevant decisions surfaced.</div>}
                  </div>
                </div>

                <div className="panel" style={{ padding: 12 }}>
                  <div className="section-title" style={{ marginBottom: 8 }}>// top_risk</div>
                  {data.top_risk ? (
                    <div className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
                      <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center' }}>
                        <span className={`badge badge-${data.top_risk.severity === 'high' ? 'high' : data.top_risk.severity === 'med' ? 'med' : 'low'}`}>{data.top_risk.severity}</span>
                        <strong>{data.top_risk.area}</strong>
                        <button className="btn" style={{ marginLeft: 'auto' }} onClick={() => onOpenRisk?.(data.top_risk!.area)}>open</button>
                      </div>
                      <div className="muted" style={{ fontSize: 12 }}>{data.top_risk.summary}</div>
                      <div className="muted" style={{ fontSize: 11 }}>{data.top_risk.recommended_first_action}</div>
                      <EvidenceChips ids={data.top_risk.evidence} evidenceMap={evidenceMap} onOpen={openEvidence} />
                    </div>
                  ) : <div className="muted">No top risk surfaced for this baseline.</div>}
                </div>
              </div>

              <div className="panel" style={{ padding: 12 }}>
                <div className="section-title" style={{ marginBottom: 8 }}>// open_questions</div>
                <div style={{ display: 'grid', gap: 10 }}>
                  {data.open_questions?.length ? data.open_questions.map((item, idx) => (
                    <div key={`${item.question}-${idx}`} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
                      <strong>{item.question}</strong>
                      <div className="muted" style={{ fontSize: 12 }}>{item.next_step}</div>
                      <EvidenceChips ids={item.derived_from} evidenceMap={evidenceMap} onOpen={openEvidence} />
                    </div>
                  )) : <div className="muted">No open questions surfaced.</div>}
                </div>
              </div>

              {!!data.fallback_notes?.length && (
                <div className="panel" style={{ padding: 12 }}>
                  <div className="section-title" style={{ marginBottom: 8 }}>// fallback_notes</div>
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {data.fallback_notes.map((note, idx) => <li key={idx} className="muted">{note}</li>)}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  )
}

function InfoCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="insight-card">
      <div className="insight-title">{title}</div>
      <div className="insight-text">{text}</div>
    </div>
  )
}

function EvidenceChips({ ids, evidenceMap, onOpen }: { ids: string[]; evidenceMap: Map<string, ReacquaintanceEvidenceItem>; onOpen: (id: string) => void }) {
  if (!ids?.length) return null
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
      {ids.map((id) => {
        const item = evidenceMap.get(id)
        return (
          <button key={id} className="btn" style={{ fontSize: 11, padding: '4px 8px' }} onClick={() => onOpen(id)}>
            {item?.type || 'ref'}: {item?.label || id}
          </button>
        )
      })}
    </div>
  )
}
