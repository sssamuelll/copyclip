import type { ChangeItem } from '../types/api'

export function ChangesPage({ items, focusCommitId }: { items: ChangeItem[]; focusCommitId?: string | null }) {
  const sorted = [...items]
  const highImpact = sorted.slice(0, 3)
  const latest = sorted[0]

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
          <span className="section-title">// commit_timeline</span>
          <span className="muted" style={{ fontSize: 11 }}>{items.length} commits indexed</span>
        </div>
        {sorted.map((c) => {
          const focused = !!focusCommitId && c.sha.startsWith(focusCommitId)
          return (
            <div key={c.sha} className="row-item" style={focused ? { background: 'rgba(16,185,129,.15)' } : undefined}>
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
