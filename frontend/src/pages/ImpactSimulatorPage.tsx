import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { FileItem, ImpactResult } from '../types/api'

export function ImpactSimulatorPage() {
  const [files, setFiles] = useState<FileItem[]>([])
  const [search, setSearch] = useState('')
  const [impact, setImpact] = useState<ImpactResult | null>(null)
  const [selectedPath, setSelectedPath] = useState<string>('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.files().then((res) => setFiles(res.items))
  }, [])

  const filtered = useMemo(
    () => files.filter((f) => f.path.toLowerCase().includes(search.toLowerCase())).slice(0, 30),
    [files, search]
  )

  const analyzeImpact = async (path: string) => {
    setSelectedPath(path)
    setLoading(true)
    try {
      const res = await api.impact(path)
      setImpact(res)
    } finally {
      setLoading(false)
    }
  }

  const blastCount = impact?.impacted_modules.length ?? 0
  const severity: 'low' | 'med' | 'high' = blastCount >= 6 ? 'high' : blastCount >= 3 ? 'med' : 'low'

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">Propagation Oracle</h2>
      </div>

      <div className="narrative-grid">
        <div className="insight-card">
          <div className="insight-title">// what_it_does</div>
          <div className="insight-text">Trace how a local intervention may propagate through modules, relationships, and dependency pathways.</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// why_it_matters</div>
          <div className="insight-text">No file moves alone. In agentic codebases, small edits can silently disturb distant surfaces.</div>
        </div>
        <div className="insight-card">
          <div className="insight-title">// suggested_action</div>
          <div className="insight-text">Run propagation before major edits and gate high-blast changes with tests and decision review.</div>
        </div>
      </div>

      <div className="split" style={{ gridTemplateColumns: '1fr 1.2fr' }}>
        <div className="section-panel">
          <div className="section-header">
            <span className="section-title">// target_surface</span>
          </div>
          <div style={{ padding: 12 }}>
            <input
              type="text"
              placeholder="select a file or module to trace…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: '100%', background: 'var(--bg)', color: 'var(--text-primary)', border: '1px solid var(--border)', padding: 8 }}
            />
          </div>
          <div style={{ maxHeight: '52vh', overflowY: 'auto' }}>
            {filtered.map((f) => (
              <div
                key={f.path}
                className="row-item"
                style={selectedPath === f.path ? { background: 'var(--bg-active)' } : undefined}
                onClick={() => analyzeImpact(f.path)}
              >
                <span className="commit-msg">{f.path}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="section-panel">
          <div className="section-header">
            <span className="section-title">// propagation_field</span>
            {impact && <span className={`badge badge-${severity}`}>{severity}</span>}
          </div>

          <div style={{ padding: 14, display: 'grid', gap: 12 }}>
            {!impact && !loading && <div className="muted">Select a system surface to reveal its propagation field.</div>}
            {loading && <div className="muted">Tracing disturbance through the graph…</div>}

            {impact && (
              <>
                <div className="panel" style={{ padding: 12 }}>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>target_module</div>
                  <div style={{ fontSize: 18, color: 'var(--accent-cyan)' }}>{impact.target_module}</div>
                  <div className="muted" style={{ marginTop: 6, fontSize: 12 }}>impacted modules: {blastCount}</div>
                </div>

                <div className="panel" style={{ padding: 12 }}>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 8 }}>disturbance_path</div>
                  {blastCount === 0 ? (
                    <div className="muted">No downstream dependents detected. Low systemic turbulence.</div>
                  ) : (
                    <div style={{ display: 'grid', gap: 8 }}>
                      {impact.impacted_modules.map((m) => (
                        <div key={m} className="row-item" style={{ border: '1px solid var(--border)', margin: 0 }}>
                          <span style={{ color: 'var(--accent-red)' }}>→</span>
                          <span>{m}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="panel" style={{ padding: 12, borderColor: 'var(--accent-amber)', background: 'rgba(245,158,11,.06)' }}>
                  <div style={{ color: 'var(--accent-amber)', fontSize: 12, marginBottom: 6 }}>oracle_note</div>
                  <div style={{ fontSize: 13 }}>
                    {blastCount >= 6
                      ? 'High propagation. Gate merge with targeted regression tests and an oracle review of intent alignment.'
                      : blastCount >= 3
                        ? 'Moderate propagation. Validate connected interfaces before the change lands.'
                        : 'Low propagation. Validate local behavior and proceed with normal checks.'}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
