import type { IssueItem } from '../types/api'

export function IssuesPage({ items }: { items: IssueItem[] }) {
  return (
    <div className="page">
      <h2>Project Issues</h2>
      <div className="list">
        {!items.length && <p>No issues found.</p>}
        {items.map((it) => (
          <div key={it.id} className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <a href={it.url} target="_blank" rel="noreferrer" style={{ fontWeight: 'bold', fontSize: '1.1rem' }}>
                  #{it.id} {it.title}
                </a>
                <div style={{ marginTop: 4, opacity: 0.8 }}>
                  <span>by {it.author}</span> • <span>{it.status}</span> • <span>{new Date(it.created_at).toLocaleDateString()}</span>
                </div>
              </div>
              <span className={`badge ${it.status}`} style={{ textTransform: 'uppercase', fontSize: '0.7rem' }}>
                {it.source}
              </span>
            </div>
            {it.labels.length > 0 && (
              <div style={{ marginTop: 8, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {it.labels.map((l) => (
                  <span key={l} className="label-tag" style={{ fontSize: '0.7rem', background: '#333', padding: '2px 6px', borderRadius: 4 }}>
                    {l}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
