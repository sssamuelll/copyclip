import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import type {
  CognitiveLoadItem,
  DebtBreakdown,
  DebtFactor,
  DebtScopeKind,
  DebtSeverity,
  RemediationCandidate,
  RemediationPlan,
  RemediationReadFirstItem,
} from '../types/api'
import { fogClass } from '../utils/debt'

type SelectedScope = {
  kind: DebtScopeKind
  id: string
  label: string
}

type EmptyKind = 'not_indexed' | 'indexed_no_debt' | 'network_error'

const ANALYZE_POLL_MS = 3000
const ANALYZE_TIMEOUT_MS = 10 * 60 * 1000

export function DebtNavigatorPage({ onNotify }: { onNotify?: (msg: string) => void }) {
  const [modules, setModules] = useState<CognitiveLoadItem[]>([])
  const [loadingModules, setLoadingModules] = useState(true)
  const [selected, setSelected] = useState<SelectedScope | null>(null)
  const [breakdown, setBreakdown] = useState<DebtBreakdown | null>(null)
  const [plan, setPlan] = useState<RemediationPlan | null>(null)
  const [loadingSelected, setLoadingSelected] = useState(false)
  const [error, setError] = useState('')
  const [empty, setEmpty] = useState<EmptyKind | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeElapsed, setAnalyzeElapsed] = useState(0)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const analyzeStartRef = useRef(0)

  const stopPolling = () => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    if (tickRef.current !== null) {
      clearInterval(tickRef.current)
      tickRef.current = null
    }
    setAnalyzing(false)
    setAnalyzeElapsed(0)
  }

  const loadModules = async () => {
    setLoadingModules(true)
    try {
      const [load, ov] = await Promise.all([api.cognitiveLoad(), api.overview()])
      setModules(load.items)
      if (load.items.length === 0) {
        setEmpty(ov.files === 0 ? 'not_indexed' : 'indexed_no_debt')
      } else {
        setEmpty(null)
        if (!selected) {
          const top = load.items[0]
          setSelected({ kind: 'module', id: top.module, label: top.module })
        }
      }
      setError('')
    } catch (e) {
      setEmpty('network_error')
      setError(e instanceof Error ? e.message : 'Failed to load cognitive load map')
    } finally {
      setLoadingModules(false)
    }
  }

  const loadSelected = async (scope: SelectedScope) => {
    setLoadingSelected(true)
    setError('')
    try {
      const response = await api.debtRemediation(scope.kind, scope.id)
      setBreakdown(response.breakdown)
      setPlan(response.plan)
    } catch (e) {
      setBreakdown(null)
      setPlan(null)
      const msg = e instanceof Error ? e.message : 'failed to load debt breakdown'
      onNotify?.(`could not load ${scope.label}: ${msg}`)
    } finally {
      setLoadingSelected(false)
    }
  }

  const startPolling = () => {
    if (pollRef.current !== null) return
    setAnalyzing(true)
    analyzeStartRef.current = Date.now()
    setAnalyzeElapsed(0)
    tickRef.current = setInterval(() => {
      setAnalyzeElapsed(Math.floor((Date.now() - analyzeStartRef.current) / 1000))
    }, 1000)
    pollRef.current = setInterval(async () => {
      if (Date.now() - analyzeStartRef.current > ANALYZE_TIMEOUT_MS) {
        stopPolling()
        onNotify?.('analyze timeout — check Ops for current status')
        return
      }
      try {
        const status = await api.analyzeStatus()
        const latest = status.items[0]
        if (!latest) return
        if (latest.status === 'completed') {
          stopPolling()
          loadModules()
        } else if (latest.status === 'failed' || latest.status === 'canceled') {
          stopPolling()
          onNotify?.(`analyze ${latest.status} — see Ops for diagnostics`)
        }
      } catch {
        // swallow transient polling errors; timeout catches sustained failures
      }
    }, ANALYZE_POLL_MS)
  }

  const onRunAnalyze = async () => {
    if (analyzing) return
    try {
      const res = await api.startAnalyzeJob()
      if (res.already_running) {
        onNotify?.('analyze already running — refresh in a moment')
      } else {
        onNotify?.('analyze started — this can take a couple of minutes')
      }
      startPolling()
    } catch {
      onNotify?.('failed to start analyze — see Ops for diagnostics')
    }
  }

  useEffect(() => {
    loadModules()
    return () => {
      if (pollRef.current !== null) clearInterval(pollRef.current)
      if (tickRef.current !== null) clearInterval(tickRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selected) {
      setBreakdown(null)
      setPlan(null)
      return
    }
    loadSelected(selected)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.kind, selected?.id])

  const topCandidates = useMemo(() => plan?.remediation_candidates || [], [plan])

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">debt navigator</h2>
      </div>

      <div className="section-panel">
        <div className="section-header">
          <span className="section-title">// unfamiliar_code</span>
          {breakdown && (
            <span className={`badge ${fogClass({ severity: breakdown.score.severity })}`} style={{ marginLeft: 8 }}>
              {breakdown.score.severity} · {breakdown.score.value.toFixed(1)}
            </span>
          )}
        </div>

        <div style={{ padding: 12, display: 'grid', gap: 12 }}>
          <div className="muted" style={{ maxWidth: 880 }}>
            Inspect dark areas by module, see why they are dark, and jump to the smallest next action that reduces uncertainty.
          </div>
          {empty && (
            <EmptyStatePanel
              kind={empty}
              analyzing={analyzing}
              elapsedSec={analyzeElapsed}
              loading={loadingModules}
              onRunAnalyze={onRunAnalyze}
              onRetry={loadModules}
            />
          )}
          {!empty && error && <div className="error">{error}</div>}

          <div style={{ display: empty ? 'none' : 'grid', gap: 12, gridTemplateColumns: 'minmax(280px, 360px) minmax(0, 1fr)' }}>
            <div className="panel" style={{ padding: 12, display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div className="section-title">// dark_modules</div>
                <span className="badge">{modules.length}</span>
                <button className="btn" style={{ marginLeft: 'auto' }} onClick={() => loadModules()} disabled={loadingModules}>
                  {loadingModules ? 'refreshing…' : 'refresh'}
                </button>
              </div>
              {modules.length ? (
                <div style={{ display: 'grid', gap: 8 }}>
                  {modules.map((item) => (
                    <button
                      key={item.module}
                      className="row-item"
                      style={{
                        margin: 0,
                        border: selected?.kind === 'module' && selected.id === item.module ? '1px solid var(--accent-cyan)' : '1px solid var(--border)',
                        textAlign: 'left',
                        background: selected?.kind === 'module' && selected.id === item.module ? 'var(--accent-cyan-soft)' : 'transparent',
                      }}
                      onClick={() => setSelected({ kind: 'module', id: item.module, label: item.module })}
                    >
                      <div style={{ display: 'grid', gap: 4, width: '100%' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <strong>{item.module}</strong>
                          <span className={`badge ${fogClass(item)}`} style={{ marginLeft: 'auto' }}>{item.severity ?? item.fog_level}</span>
                        </div>
                        <div className="muted" style={{ fontSize: 11 }}>
                          debt {item.cognitive_debt_score.toFixed(1)} · files {item.files} · churn {item.churn}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="muted">No cognitive debt data yet. Run analyze first.</div>
              )}
            </div>

            <div style={{ display: 'grid', gap: 12 }}>
              {!selected ? (
                <div className="muted">Select a module to inspect its debt breakdown and recommended next actions.</div>
              ) : loadingSelected && !breakdown ? (
                <div className="muted">loading…</div>
              ) : breakdown ? (
                <>
                  <VerdictCard breakdown={breakdown} scopeLabel={selected.label} />
                  <FactorBreakdownGrid factors={breakdown.factor_breakdown} />
                  {plan && <RemediationPanel plan={plan} topCandidates={topCandidates} onOpenFile={(path) => {
                    setSelected({ kind: 'file', id: path, label: path })
                    onNotify?.(`drilling into ${path}`)
                  }} />}
                  {plan && <ReadFirstPanel items={plan.read_first} />}
                  {selected.kind === 'module' && (
                    <ModuleFileList
                      breakdown={breakdown}
                      onPickFile={(path) => setSelected({ kind: 'file', id: path, label: path })}
                    />
                  )}
                </>
              ) : (
                <div className="muted">No breakdown available for this scope.</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function EmptyStatePanel({
  kind,
  analyzing,
  elapsedSec,
  loading,
  onRunAnalyze,
  onRetry,
}: {
  kind: EmptyKind
  analyzing: boolean
  elapsedSec: number
  loading: boolean
  onRunAnalyze: () => void
  onRetry: () => void
}) {
  type CTA = { label: string; loadingLabel: string; primary: boolean; onClick: () => void }
  let variant: { title: string; body: string; cta: CTA | null }
  if (analyzing) {
    variant = {
      title: `// analyzing… (${elapsedSec}s)`,
      body: 'copyclip is computing cognitive debt across the project. Modules will appear here when the job completes.',
      cta: null,
    }
  } else if (kind === 'not_indexed') {
    variant = {
      title: '// no_index_yet',
      body: 'This project has not been indexed. Run analyze to compute cognitive debt across modules.',
      cta: { label: 'run analyze', loadingLabel: 'loading…', primary: true, onClick: onRunAnalyze },
    }
  } else if (kind === 'indexed_no_debt') {
    variant = {
      title: '// clean_signal',
      body: "No cognitive debt detected. Either the analyzer hasn't found any dark zones, or your project is in unusually good shape.",
      cta: { label: 'refresh', loadingLabel: 'refreshing…', primary: false, onClick: onRetry },
    }
  } else {
    variant = {
      title: '// load_failed',
      body: 'Could not reach the intelligence server. Check that copyclip start is running, then retry.',
      cta: { label: 'retry', loadingLabel: 'retrying…', primary: true, onClick: onRetry },
    }
  }

  return (
    <div
      className="panel"
      style={{
        padding: 24,
        maxWidth: 520,
        margin: '0 auto',
        display: 'grid',
        gap: 12,
        justifyItems: 'center',
        textAlign: 'center',
      }}
    >
      <div className="section-title">{variant.title}</div>
      <div className="muted" style={{ fontSize: 13, maxWidth: 420 }}>{variant.body}</div>
      {variant.cta && (
        <button
          className={variant.cta.primary ? 'btn primary' : 'btn'}
          onClick={variant.cta.onClick}
          disabled={loading}
        >
          {loading ? variant.cta.loadingLabel : variant.cta.label}
        </button>
      )}
    </div>
  )
}

function VerdictCard({ breakdown, scopeLabel }: { breakdown: DebtBreakdown; scopeLabel: string }) {
  return (
    <div className="insight-card" style={{ margin: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <div className="insight-title">// verdict</div>
        <span className={`badge ${fogClass({ severity: breakdown.score.severity })}`}>{breakdown.score.severity}</span>
        <span className="badge" style={{ marginLeft: 'auto' }}>confidence: {breakdown.score.confidence}</span>
      </div>
      <div className="insight-text" style={{ marginTop: 8 }}>
        <strong>{scopeLabel}</strong>
        <span className="muted" style={{ marginLeft: 8 }}>
          debt {breakdown.score.value.toFixed(1)} / 100 · signal coverage {(breakdown.score.signal_coverage * 100).toFixed(0)}%
        </span>
      </div>
      <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
        contract {breakdown.meta.contract_version} · scope {breakdown.meta.scope_kind}
      </div>
    </div>
  )
}

function FactorBreakdownGrid({ factors }: { factors: DebtFactor[] }) {
  return (
    <div className="insight-card" style={{ margin: 0 }}>
      <div className="insight-title">// factor_breakdown</div>
      <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
        {factors.map((f) => (
          <FactorRow key={f.factor_id} factor={f} />
        ))}
      </div>
    </div>
  )
}

function FactorRow({ factor }: { factor: DebtFactor }) {
  const normalized = factor.normalized_contribution ?? 0
  const available = factor.signal_available
  return (
    <div style={{ padding: 8, border: '1px solid var(--border)', borderRadius: 2 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <strong>{factor.label}</strong>
        <span className="muted" style={{ fontSize: 11 }}>weight {factor.weight.toFixed(2)}</span>
        <span className={`badge ${available ? (normalized >= 60 ? 'fog-high' : normalized >= 30 ? 'fog-med' : 'fog-low') : 'fog-low'}`} style={{ marginLeft: 'auto' }}>
          {available ? `${normalized.toFixed(0)}` : 'unavailable'}
        </span>
      </div>
      <div style={{ position: 'relative', height: 4, background: 'var(--accent-cyan-soft)', marginTop: 6, borderRadius: 2 }}>
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: `${available ? Math.min(100, normalized) : 0}%`,
            background: available ? 'var(--accent-cyan)' : 'transparent',
            borderRadius: 2,
          }}
        />
      </div>
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{factor.rationale}</div>
      {factor.evidence.length > 0 && (
        <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
          {factor.evidence.slice(0, 6).map((ev) => (
            <span key={ev} className="badge" style={{ fontSize: 10 }}>{ev}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function RemediationPanel({ plan, topCandidates, onOpenFile }: { plan: RemediationPlan; topCandidates: RemediationCandidate[]; onOpenFile?: (path: string) => void }) {
  return (
    <div className="insight-card" style={{ margin: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <div className="insight-title">// next_actions</div>
        {plan.top_factors.length > 0 && (
          <span className="muted" style={{ fontSize: 11 }}>
            top factors: {plan.top_factors.slice(0, 3).join(', ')}
          </span>
        )}
        <span className="badge" style={{ marginLeft: 'auto' }}>
          est. impact {plan.expected_total_impact.score_delta.toFixed(1)} · {plan.expected_total_impact.confidence}
        </span>
      </div>
      <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
        {topCandidates.length ? topCandidates.map((c) => (
          <div key={c.id} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start', padding: 10 }}>
            <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <strong>{c.label}</strong>
              <span className={`badge ${c.expected_impact.score_delta <= -8 ? 'fog-high' : c.expected_impact.score_delta <= -3 ? 'fog-med' : 'fog-low'}`} style={{ marginLeft: 'auto' }}>
                Δ {c.expected_impact.score_delta.toFixed(1)}
              </span>
            </div>
            <div className="muted" style={{ fontSize: 12 }}>{c.rationale}</div>
            <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
              <span className="badge" style={{ fontSize: 10 }}>{c.action_type.replace(/_/g, ' ')}</span>
              {c.reduces_factors.map((f) => (
                <span key={f} className="badge" style={{ fontSize: 10 }}>{f}</span>
              ))}
            </div>
            {c.evidence.length > 0 && (
              <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                {c.evidence.slice(0, 6).map((ev) => (
                  <EvidencePill key={ev} ev={ev} onOpenFile={onOpenFile} />
                ))}
              </div>
            )}
          </div>
        )) : (
          <div className="muted">No remediation candidates. Either debt is already low or no signals exceed the activation floors.</div>
        )}
      </div>
      {plan.notes.map((note, idx) => (
        <div key={`${note.kind}-${idx}`} className="muted" style={{ fontSize: 11, marginTop: 8 }}>
          {String(note.message || '')}
        </div>
      ))}
    </div>
  )
}

function EvidencePill({ ev, onOpenFile }: { ev: string; onOpenFile?: (path: string) => void }) {
  const isFile = ev.startsWith('file:')
  if (isFile && onOpenFile) {
    const path = ev.slice(5)
    return (
      <button className="badge" style={{ fontSize: 10, cursor: 'pointer' }} onClick={() => onOpenFile(path)}>{ev}</button>
    )
  }
  return <span className="badge" style={{ fontSize: 10 }}>{ev}</span>
}

function ReadFirstPanel({ items }: { items: RemediationReadFirstItem[] }) {
  if (!items.length) return null
  return (
    <div className="insight-card" style={{ margin: 0 }}>
      <div className="insight-title">// read_first</div>
      <ol style={{ margin: 0, paddingLeft: 18, marginTop: 8, display: 'grid', gap: 6 }}>
        {items.map((item, idx) => (
          <li key={`${item.id}-${idx}`}>
            <div>
              <span className="badge" style={{ fontSize: 10, marginRight: 6 }}>{item.kind}</span>
              <span style={{ fontSize: 12 }}>{renderReadFirstTarget(item)}</span>
            </div>
            <div className="muted" style={{ fontSize: 11 }}>{item.reason}</div>
          </li>
        ))}
      </ol>
    </div>
  )
}

function renderReadFirstTarget(item: RemediationReadFirstItem) {
  if (item.kind === 'commit' && item.sha) {
    const shortSha = item.sha.slice(0, 7)
    const label = item.author_kind ? `${shortSha} (${item.author_kind})` : shortSha
    return label
  }
  if (item.kind === 'decision' && item.decision_id !== undefined) {
    return `decision #${item.decision_id}`
  }
  return item.id
}

function ModuleFileList({ breakdown, onPickFile }: { breakdown: DebtBreakdown; onPickFile: (path: string) => void }) {
  const fileNote = breakdown.notes.find((n) => n.kind === 'module_file_scores') as { kind: string; items: Array<{ path: string; score: number; severity: DebtSeverity | string }> } | undefined
  if (!fileNote?.items?.length) return null
  const sorted = [...fileNote.items].sort((a, b) => b.score - a.score)
  return (
    <div className="insight-card" style={{ margin: 0 }}>
      <div className="insight-title">// member_files</div>
      <div style={{ display: 'grid', gap: 6, marginTop: 8 }}>
        {sorted.map((row) => (
          <button
            key={row.path}
            className="row-item"
            onClick={() => onPickFile(row.path)}
            style={{ margin: 0, border: '1px solid var(--border)', textAlign: 'left' }}
          >
            <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <strong style={{ fontSize: 12 }}>{row.path}</strong>
              <span className={`badge ${fogClass({ severity: row.severity })}`} style={{ marginLeft: 'auto' }}>
                {row.severity} · {row.score.toFixed(1)}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
