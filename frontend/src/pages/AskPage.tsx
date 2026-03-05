import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type { AdvisorConflict, AskCitation, AskResponse } from '../types/api'

export function AskPage({ onOpenCitation, onNotify }: { onOpenCitation: (c: AskCitation) => void; onNotify?: (msg: string) => void }) {
  const [q, setQ] = useState('What are the highest-risk areas right now?')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AskResponse | null>(null)
  const [advisorConflicts, setAdvisorConflicts] = useState<AdvisorConflict[]>([])
  const [error, setError] = useState('')

  const grouped = useMemo(() => {
    const citations = result?.citations || []
    return {
      decision: citations.filter((c) => c.type === 'decision'),
      risk: citations.filter((c) => c.type === 'risk'),
      commit: citations.filter((c) => c.type === 'commit'),
    }
  }, [result])

  const runAsk = async () => {
    if (!q.trim()) return
    setLoading(true)
    setError('')
    setAdvisorConflicts([])
    try {
      const intent = q.trim()
      const [res, advisor] = await Promise.all([
        api.ask(intent),
        api.decisionAdvisorCheck(intent, []),
      ])
      setResult(res)
      setAdvisorConflicts(advisor?.conflicts || [])
      if ((advisor?.conflicts || []).length > 0) {
        onNotify?.(`Advisor detected ${(advisor?.conflicts || []).length} potential decision conflict(s)`)
      } else {
        onNotify?.(res.grounded ? 'Grounded answer ready' : 'Low-grounding answer: review citations')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ask failed')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">ask project</h2>
      </div>

      <div className="narrative-grid">
        <div className="insight-card">
          <div className="insight-title">// what_changed</div>
          <div className="insight-text">Ask reads project metadata and returns a grounded answer with citations.</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// why_it_matters</div>
          <div className="insight-text">Without grounding, AI responses can drift from real project decisions and risk signals.</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// suggested_action</div>
          <div className="insight-text">Prefer answers with citations, then jump directly to the referenced entities.</div>
        </div>
      </div>

      <div className="split" style={{ gridTemplateColumns: '1.2fr 1fr' }}>
        <div className="section-panel">
          <div className="section-header">
            <span className="section-title">// prompt</span>
          </div>
          <div style={{ padding: 14, display: 'grid', gap: 10 }}>
            <textarea
              value={q}
              onChange={(e) => setQ(e.target.value)}
              rows={6}
              style={{ width: '100%', background: 'var(--bg)', color: 'var(--text-primary)', border: '1px solid var(--border)', padding: 10 }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="muted" style={{ fontSize: 12 }}>{q.trim().length} chars</span>
              <button className="btn primary" onClick={runAsk} disabled={loading}>{loading ? 'asking…' : 'ask'}</button>
            </div>
            {error && <div className="error">{error}</div>}
          </div>
        </div>

        <div className="section-panel">
          <div className="section-header">
            <span className="section-title">// answer_state</span>
            {result && (
              <span className={`badge ${result.grounded ? 'badge-low' : 'badge-high'}`}>
                {result.grounded ? 'grounded' : 'low grounding'}
              </span>
            )}
          </div>
          <div style={{ padding: 14, display: 'grid', gap: 10 }}>
            {!result && !loading && <div className="muted">Run a query to get a grounded project answer.</div>}
            {loading && <div className="muted">Querying project graph and intelligence DB...</div>}
            {result && (
              <>
                <div className="panel" style={{ padding: 10, fontSize: 13, lineHeight: 1.5 }}>{result.answer}</div>
                <div className="muted" style={{ fontSize: 12 }}>
                  citations: {result.citations.length} (decisions: {grouped.decision.length}, risks: {grouped.risk.length}, commits: {grouped.commit.length})
                </div>
                {!result.grounded && (
                  <div className="panel" style={{ padding: 10, borderColor: 'var(--accent-amber)', background: 'rgba(245,158,11,.08)' }}>
                    <div style={{ color: 'var(--accent-amber)', fontSize: 12, marginBottom: 6 }}>guardrail</div>
                    <div style={{ fontSize: 12 }}>Answer has low grounding. Validate via citations before acting.</div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {advisorConflicts.length > 0 && (
        <div className="section-panel">
          <div className="section-header">
            <span className="section-title">// decision_advisor_conflicts</span>
            <span className="badge badge-high">{advisorConflicts.length} conflicts</span>
          </div>
          <div style={{ display: 'grid', gap: 0 }}>
            {advisorConflicts.map((c) => (
              <div key={`adv-${c.decision_id}`} className="row-item" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 6 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', width: '100%' }}>
                  <span className="status-badge status-proposed">#dec-{String(c.decision_id).padStart(3, '0')}</span>
                  <span className="muted" style={{ fontSize: 12 }}>confidence {Math.round((c.confidence || 0) * 100)}%</span>
                  <button className="btn" style={{ marginLeft: 'auto' }} onClick={() => onOpenCitation({ type: 'decision', id: c.decision_id, label: `decision #${c.decision_id}` })}>open decision</button>
                </div>
                <div style={{ fontSize: 12 }}>{c.title}</div>
                <div className="muted" style={{ fontSize: 12 }}>{c.why_conflict}</div>
                <div className="muted" style={{ fontSize: 12 }}>suggested: {c.suggested_alternative}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {result && (
        <div className="section-panel">
          <div className="section-header">
            <span className="section-title">// citations</span>
          </div>
          <div style={{ display: 'grid', gap: 0 }}>
            {result.citations.map((c, i) => (
              <div key={`${c.type}-${c.id}-${i}`} className="row-item" style={{ justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span className={`badge ${c.type === 'decision' ? 'badge-low' : c.type === 'risk' ? 'badge-high' : 'badge-med'}`}>{c.type}</span>
                  <span style={{ fontSize: 12 }}>{c.label}</span>
                </div>
                <button className="btn" onClick={() => onOpenCitation(c)}>open</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
