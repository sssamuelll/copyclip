import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { ArchaeologyResponse, ChangeItem, FileItem } from '../types/api'

export function ChangesPage({
  items,
  focusCommitId,
  onOpenDecision,
}: {
  items: ChangeItem[]
  focusCommitId?: string | null
  onOpenDecision?: (id: number) => void
}) {
  const sorted = [...items]
  const highImpact = sorted.slice(0, 3)
  const latest = sorted[0]

  const [files, setFiles] = useState<FileItem[]>([])
  const [fileQuery, setFileQuery] = useState('')
  const [arch, setArch] = useState<ArchaeologyResponse | null>(null)
  const [archLoading, setArchLoading] = useState(false)
  const [archError, setArchError] = useState('')

  useEffect(() => {
    api.files().then((res) => setFiles(res.items)).catch(() => {})
  }, [])

  const suggestions = useMemo(() => files.filter((f) => f.path.toLowerCase().includes(fileQuery.toLowerCase())).slice(0, 20), [files, fileQuery])

  const runArchaeology = async () => {
    if (!fileQuery.trim()) return
    setArchError('')
    setArchLoading(true)
    try {
      const res = await api.archaeology(fileQuery.trim())
      setArch(res)
    } catch (e) {
      setArch(null)
      setArchError(e instanceof Error ? e.message : 'Archaeology request failed')
    } finally {
      setArchLoading(false)
    }
  }

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">changes</h2>
      </div>

      <div className="narrative-grid">
        <div className="insight-card">
          <div className="insight-title">// what_changed</div>
          <div className="insight-text">{latest ? `${latest.sha.slice(0, 7)} touched: ${latest.message}` : 'No commit timeline indexed yet.'}</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// why_it_matters</div>
          <div className="insight-text">Recent change velocity can hide architectural drift when AI agents ship fast.</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// suggested_action</div>
          <div className="insight-text">Review high-impact commits first, then reconcile with open decisions and top risks.</div>
        </div>
      </div>

      <div className="section-panel">
        <div className="section-header">
          <span className="section-title" style={{ color: 'var(--accent-red)' }}>// high_impact_changes</span>
        </div>
        {highImpact.map((c) => (
          <div key={c.sha} className="row-item">
            <span className="commit-sha" style={{ color: 'var(--accent-red)' }}>{c.sha.slice(0, 7)}</span>
            <span className="commit-msg">{c.message}</span>
            <span className="badge badge-high">impact</span>
          </div>
        ))}
      </div>

      <div className="section-panel">
        <div className="section-header">
          <span className="section-title">// git_archaeology</span>
        </div>
        <div style={{ padding: 12, display: 'grid', gap: 10 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              list="arch-file-list"
              value={fileQuery}
              onChange={(e) => setFileQuery(e.target.value)}
              placeholder="enter file path (e.g. frontend/src/App.tsx)"
              style={{ flex: 1, background: 'var(--bg)', color: 'var(--text-primary)', border: '1px solid var(--border)', padding: 8 }}
            />
            <button className="btn" onClick={runArchaeology} disabled={archLoading || !fileQuery.trim()}>
              {archLoading ? 'loading…' : 'inspect'}
            </button>
            <datalist id="arch-file-list">
              {suggestions.map((s) => (
                <option key={s.path} value={s.path} />
              ))}
            </datalist>
          </div>

          {archError && <div className="error">{archError}</div>}

          {arch && (
            <div className="split" style={{ gridTemplateColumns: '1fr 1fr' }}>
              <div className="panel" style={{ padding: 10 }}>
                <div className="section-title" style={{ marginBottom: 8 }}>// commits_for_file</div>
                <div style={{ display: 'grid', gap: 8 }}>
                  {arch.commits.length ? arch.commits.slice(0, 8).map((c) => (
                    <div key={c.sha} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 0 }}>
                        <span className="commit-sha">{c.sha.slice(0, 7)}</span>
                        <span className="commit-msg" style={{ minWidth: 0 }}>{c.message}</span>
                      </div>
                      <button
                        className="btn"
                        onClick={() => {
                          const short = c.sha.slice(0, 7)
                          const el = document.querySelector(`[data-commit-sha=\"${short}\"]`) as HTMLElement | null
                          if (el) {
                            el.scrollIntoView({ behavior: 'smooth', block: 'center' })
                            el.style.background = 'rgba(16,185,129,.22)'
                            window.setTimeout(() => { el.style.background = '' }, 1200)
                          }
                        }}
                      >
                        jump
                      </button>
                    </div>
                  )) : <div className="muted">No git history found for this file.</div>}
                </div>
              </div>

              <div className="panel" style={{ padding: 10 }}>
                <div className="section-title" style={{ marginBottom: 8 }}>// related_decisions</div>
                <div style={{ display: 'grid', gap: 8 }}>
                  {arch.related_decisions.length ? arch.related_decisions.map((d) => (
                    <div key={d.id} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', width: '100%' }}>
                        <span className={`status-badge status-${normalizeStatus(d.status)}`}>{d.status}</span>
                        <span className="muted" style={{ fontSize: 11 }}>#dec-{String(d.id).padStart(3, '0')}</span>
                        <button className="btn" style={{ marginLeft: 'auto' }} onClick={() => onOpenDecision?.(d.id)}>open</button>
                      </div>
                      <div style={{ fontSize: 12 }}>{d.title}</div>
                      <div className="muted" style={{ fontSize: 11 }}>refs: {d.matched_refs.map((r) => `${r.ref_type}:${r.ref_value}`).join(', ')}</div>
                    </div>
                  )) : <div className="muted">No linked decisions found for this file/commit history.</div>}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="section-panel">
        <div className="section-header">
          <span className="section-title">// commit_timeline</span>
          <span className="muted" style={{ fontSize: 11 }}>{items.length} commits indexed</span>
        </div>
        {sorted.map((c) => {
          const focused = !!focusCommitId && c.sha.startsWith(focusCommitId)
          return (
            <div data-commit-sha={c.sha.slice(0, 7)} key={c.sha} className="row-item" style={focused ? { background: 'rgba(16,185,129,.15)' } : undefined}>
              <span className="commit-sha">{c.sha.slice(0, 7)}</span>
              <span className="commit-msg">{c.message}</span>
              <span className="commit-meta">{c.date?.slice(0, 19) || 'n/a'}</span>
            </div>
          )
        })}
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
