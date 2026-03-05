import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { AdvisorConflict, FileItem, IssueItem } from '../types/api'

type Mode = 'full' | 'signatures' | 'docstrings'

export function ContextBuilderPage() {
  const [files, setFiles] = useState<FileItem[]>([])
  const [issues, setIssues] = useState<IssueItem[]>([])
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set())
  const [fileModes, setFileModes] = useState<Record<string, Mode>>({})
  const [selectedIssues, setSelectedIssues] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [includeDecisions, setIncludeDecisions] = useState(true)
  const [minimize, setMinimize] = useState<'basic' | 'aggressive' | 'structural'>('basic')
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [warnings, setWarnings] = useState<string[]>([])
  const [advisorIntent, setAdvisorIntent] = useState('')
  const [advisorConflicts, setAdvisorConflicts] = useState<AdvisorConflict[]>([])
  const [advisorOverride, setAdvisorOverride] = useState(false)
  const [governanceMode, setGovernanceMode] = useState<boolean>(() => {
    try { return localStorage.getItem('copyclip.governanceMode') === '1' } catch { return false }
  })
  const [overrideReason, setOverrideReason] = useState('')

  useEffect(() => {
    api.files().then((res) => setFiles(res.items))
    api.issues().then((res) => setIssues(res.items))
  }, [])

  useEffect(() => {
    try { localStorage.setItem('copyclip.governanceMode', governanceMode ? '1' : '0') } catch {}
  }, [governanceMode])

  const filteredFiles = useMemo(() => files.filter((f) => f.path.toLowerCase().includes(search.toLowerCase())), [files, search])

  const toggleFile = (path: string) => {
    const next = new Set(selectedFiles)
    if (next.has(path)) next.delete(path)
    else next.add(path)
    setSelectedFiles(next)
    if (!fileModes[path]) setFileModes((prev) => ({ ...prev, [path]: 'full' }))
    setWarnings([])
    setAdvisorConflicts([])
    setAdvisorOverride(false)
    setOverrideReason('')
  }

  const setMode = (path: string, mode: Mode) => {
    setFileModes((prev) => ({ ...prev, [path]: mode }))
    setAdvisorConflicts([])
    setAdvisorOverride(false)
  }

  const applyModeToAllSelected = (mode: Mode) => {
    const patch: Record<string, Mode> = {}
    Array.from(selectedFiles).forEach((f) => (patch[f] = mode))
    setFileModes((prev) => ({ ...prev, ...patch }))
    setAdvisorConflicts([])
    setAdvisorOverride(false)
  }

  const toggleIssue = (id: string) => {
    const next = new Set(selectedIssues)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIssues(next)
    setWarnings([])
    setAdvisorConflicts([])
    setAdvisorOverride(false)
    setOverrideReason('')
  }

  const selectedFileObjs = useMemo(() => files.filter((f) => selectedFiles.has(f.path)), [files, selectedFiles])

  const estimatedTokens = useMemo(() => {
    // rough estimator: 1 token ~ 4 chars, mode coefficients
    const coeff = (m: Mode) => (m === 'full' ? 1 : m === 'signatures' ? 0.3 : 0.2)
    const fileTokens = selectedFileObjs.reduce((acc, f) => {
      const mode = fileModes[f.path] || 'full'
      return acc + Math.ceil((f.size * coeff(mode)) / 4)
    }, 0)
    const issuesTokens = selectedIssues.size * 220
    const decisionsTokens = includeDecisions ? 300 : 0
    return fileTokens + issuesTokens + decisionsTokens
  }, [selectedFileObjs, fileModes, selectedIssues, includeDecisions])

  const budgetState: 'ok' | 'warn' | 'risk' = estimatedTokens > 28000 ? 'risk' : estimatedTokens > 14000 ? 'warn' : 'ok'

  const handleCopy = async () => {
    setLoading(true)
    setWarnings([])
    try {
      const intent = advisorIntent.trim() || `Assemble context for ${selectedFiles.size} files and ${selectedIssues.size} issues`
      const advisor = await api.decisionAdvisorCheck(intent, Array.from(selectedFiles))
      const conflicts = advisor?.conflicts || []
      setAdvisorConflicts(conflicts)

      // First click with conflicts = review step (no copy yet)
      if (conflicts.length > 0 && !advisorOverride) {
        setAdvisorOverride(true)
        setLoading(false)
        return
      }

      // Governance mode: explicit reason required to override conflicts.
      if (conflicts.length > 0 && governanceMode && !overrideReason.trim()) {
        setWarnings(['Governance mode requires an override reason before copying context.'])
        setLoading(false)
        return
      }

      const res = await api.assembleContext({
        files: Array.from(selectedFiles),
        issues: Array.from(selectedIssues),
        include_decisions: includeDecisions,
        minimize,
      })
      await navigator.clipboard.writeText(res.context)
      if (res.warnings && res.warnings.length > 0) {
        setWarnings(res.warnings)
      }
      setCopied(true)
      setTimeout(() => setCopied(false), 2200)
      setAdvisorOverride(false)
      setOverrideReason('')
    } catch {
      alert('Failed to assemble context')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">context cart</h2>
      </div>

      <div className="narrative-grid">
        <div className="insight-card">
          <div className="insight-title">// what_changed</div>
          <div className="insight-text">Curate files/issues and tune granularity before sending context to AI.</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// why_it_matters</div>
          <div className="insight-text">Too much raw context increases token cost and dilutes signal.</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// suggested_action</div>
          <div className="insight-text">Start with signatures/docstrings for broad scope, then upgrade key files to full.</div>
        </div>
      </div>

      <div className="split" style={{ gridTemplateColumns: '1.2fr 1fr' }}>
        <div className="section-panel" style={{ minHeight: '68vh' }}>
          <div className="section-header">
            <span className="section-title">// available_context</span>
          </div>

          <div style={{ padding: 12, display: 'grid', gap: 10 }}>
            <input
              type="text"
              placeholder="search files..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', padding: 8 }}
            />

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn" onClick={() => applyModeToAllSelected('full')}>all selected → full</button>
              <button className="btn" onClick={() => applyModeToAllSelected('signatures')}>all selected → signatures</button>
              <button className="btn" onClick={() => applyModeToAllSelected('docstrings')}>all selected → docstrings</button>
            </div>
          </div>

          <div style={{ maxHeight: '40vh', overflowY: 'auto', borderTop: '1px solid var(--border)' }}>
            {filteredFiles.slice(0, 120).map((f) => {
              const selected = selectedFiles.has(f.path)
              const mode = fileModes[f.path] || 'full'
              return (
                <div key={f.path} className="row-item" style={{ alignItems: 'flex-start', flexDirection: 'column', gap: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
                    <input type="checkbox" checked={selected} onChange={() => toggleFile(f.path)} />
                    <span style={{ fontSize: 12, opacity: selected ? 1 : 0.75 }}>{f.path}</span>
                    <span className="muted" style={{ marginLeft: 'auto', fontSize: 11 }}>{Math.round(f.size / 1024)}KB</span>
                  </div>
                  {selected && (
                    <div style={{ display: 'flex', gap: 6, marginLeft: 24 }}>
                      {(['full', 'signatures', 'docstrings'] as Mode[]).map((m) => (
                        <button key={m} className="btn" style={mode === m ? { background: 'var(--bg-active)' } : undefined} onClick={() => setMode(f.path, m)}>
                          {m}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
            {filteredFiles.length > 120 && <div className="muted" style={{ padding: 12 }}>+ {filteredFiles.length - 120} more files</div>}
          </div>

          <div style={{ borderTop: '1px solid var(--border)', padding: 12 }}>
            <div className="section-title" style={{ marginBottom: 6 }}>// issues</div>
            <div style={{ maxHeight: '16vh', overflowY: 'auto', display: 'grid', gap: 6 }}>
              {issues.map((i) => (
                <label key={i.id} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12 }}>
                  <input type="checkbox" checked={selectedIssues.has(i.id)} onChange={() => toggleIssue(i.id)} />
                  <span>#{i.id} {i.title}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="section-panel" style={{ borderColor: 'var(--accent)' }}>
          <div className="section-header">
            <span className="section-title">// payload</span>
            <span className={`badge ${budgetState === 'risk' ? 'badge-high' : budgetState === 'warn' ? 'badge-med' : 'badge-low'}`}>
              {budgetState === 'risk' ? 'over budget' : budgetState === 'warn' ? 'watch budget' : 'healthy'}
            </span>
          </div>

          <div style={{ padding: 12, display: 'grid', gap: 10 }}>
            <div className="panel" style={{ padding: 10 }}>
              <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>estimated_tokens</div>
              <div style={{ fontSize: 24, fontFamily: 'JetBrains Mono, monospace' }}>{estimatedTokens.toLocaleString()}</div>
              <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                {selectedFiles.size} files · {selectedIssues.size} issues · decisions {includeDecisions ? 'on' : 'off'}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                <input type="checkbox" checked={includeDecisions} onChange={(e) => { setIncludeDecisions(e.target.checked); setAdvisorConflicts([]); setAdvisorOverride(false) }} /> include decisions
              </label>
              <select value={minimize} onChange={(e) => { setMinimize(e.target.value as any); setAdvisorConflicts([]); setAdvisorOverride(false) }} style={{ background: 'var(--bg)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}>
                <option value="basic">basic</option>
                <option value="aggressive">aggressive</option>
                <option value="structural">structural</option>
              </select>
            </div>

            <div>
              <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>advisor_intent (used for conflict checks)</div>
              <textarea
                rows={2}
                value={advisorIntent}
                onChange={(e) => { setAdvisorIntent(e.target.value); setAdvisorConflicts([]); setAdvisorOverride(false); setOverrideReason('') }}
                placeholder="e.g. Refactor dependency graph around analyzer + server API"
                style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', padding: 8 }}
              />
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
              <input type="checkbox" checked={governanceMode} onChange={(e) => { setGovernanceMode(e.target.checked); setWarnings([]) }} />
              governance mode (override requires reason)
            </label>

            <div className="table" style={{ maxHeight: '30vh' }}>
              <div className="table-header" style={{ gridTemplateColumns: '1fr 100px' }}>
                <span>selected file</span><span>mode</span>
              </div>
              {selectedFileObjs.length ? selectedFileObjs.map((f) => (
                <div key={f.path} className="table-row" style={{ gridTemplateColumns: '1fr 100px' }}>
                  <span style={{ fontSize: 12 }}>{f.path}</span>
                  <span className="muted" style={{ fontSize: 12 }}>{fileModes[f.path] || 'full'}</span>
                </div>
              )) : <div className="muted" style={{ padding: 12 }}>No files selected</div>}
            </div>

            {advisorConflicts.length > 0 && (
              <div className="panel" style={{ border: '1px solid #7f1d1d', background: 'rgba(127, 29, 29, 0.18)', padding: '10px', fontSize: '0.8rem' }}>
                <div style={{ color: '#fca5a5', fontWeight: 'bold', marginBottom: '6px' }}>Advisor conflicts detected ({advisorConflicts.length})</div>
                <div className="muted" style={{ marginBottom: 6 }}>
                  {advisorOverride ? 'Proceed is unlocked. Review conflicts and click again to copy context.' : 'Review before copy. Copy is paused until you confirm.'}
                </div>
                {advisorConflicts.map((c) => (
                  <div key={`ctx-adv-${c.decision_id}`} style={{ marginBottom: 6, borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 6 }}>
                    <div style={{ fontSize: 12 }}>#dec-{String(c.decision_id).padStart(3, '0')} · {c.title} · {Math.round((c.confidence || 0) * 100)}%</div>
                    <div className="muted">{c.why_conflict}</div>
                  </div>
                ))}

                {governanceMode && advisorOverride && (
                  <div style={{ marginTop: 8 }}>
                    <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>override_reason (required)</div>
                    <textarea
                      rows={2}
                      value={overrideReason}
                      onChange={(e) => { setOverrideReason(e.target.value); setWarnings([]) }}
                      placeholder="Explain why proceeding is still safe in this context..."
                      style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-primary)', padding: 8 }}
                    />
                  </div>
                )}
              </div>
            )}

            {warnings.length > 0 && (
              <div className="panel" style={{ border: '1px solid #92400e', background: 'rgba(146, 64, 14, 0.2)', padding: '10px', fontSize: '0.8rem' }}>
                <div style={{ color: '#fbbf24', fontWeight: 'bold', marginBottom: '6px' }}>Decision Advisor Warning</div>
                <div className="muted" style={{ marginBottom: 6 }}>Context copied, but this payload may conflict with prior architecture decisions.</div>
                {warnings.map((w, idx) => <div key={idx} style={{ marginBottom: 4 }}>• {w}</div>)}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="muted" style={{ fontSize: 12 }}>{copied ? 'copied to clipboard' : 'ready to assemble'}</span>
              <button className="btn primary" onClick={handleCopy} disabled={loading || (selectedFiles.size === 0 && selectedIssues.size === 0)}>
                {loading ? 'assembling…' : copied ? 'copied!' : advisorConflicts.length > 0 && advisorOverride ? 'proceed & copy' : 'copy context'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
