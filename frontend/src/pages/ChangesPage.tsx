import type { ChangeItem } from '../types/api'

export function ChangesPage({ items, focusCommitId }: { items: ChangeItem[]; focusCommitId?: string | null }) {
  const sorted = [...items]
  const highImpact = sorted.slice(0, 3)

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">changes</h2>
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
