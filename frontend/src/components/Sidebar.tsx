type Props = { page: string; setPage: (v: string) => void; lastIndexedText?: string }

const GROUPS = [
  {
    label: 'Understand',
    pages: [
      { id: 'atlas', label: 'atlas' },
      { id: 'architecture', label: 'architecture' },
      { id: 'impact', label: 'impact simulator' },
      { id: 'narrative', label: 'narrative' },
      { id: 'ask', label: 'ask project' },
    ]
  },
  {
    label: 'Operate',
    pages: [
      { id: 'context-builder', label: 'context builder' },
      { id: 'settings', label: 'settings' },
    ]
  },
  {
    label: 'Track',
    pages: [
      { id: 'issues', label: 'issues' },
      { id: 'risks', label: 'risks' },
      { id: 'decisions', label: 'decisions' },
      { id: 'changes', label: 'changes' },
      { id: 'ops', label: 'ops center' },
    ]
  }
]

export function Sidebar({ page, setPage, lastIndexedText }: Props) {
  return (
    <aside className="sidebar">
      <div>
        <h1>&gt; copyclip</h1>
        <nav>
          {GROUPS.map((g) => (
            <div key={g.label} className="nav-group">
              <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', opacity: 0.5, marginTop: '0.8rem', marginBottom: '0.4rem', paddingLeft: '0.5rem' }}>
                {g.label}
              </div>
              {g.pages.map((p) => (
                <button key={p.id} className={page === p.id ? 'active' : ''} onClick={() => setPage(p.id)}>
                  {p.label}
                </button>
              ))}
            </div>
          ))}
        </nav>
      </div>

      <div style={{ display: 'grid', gap: 8 }}>
        <div className="panel" style={{ padding: '8px 10px', fontSize: 12, color: 'var(--text-tertiary)' }}>/ search...</div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{lastIndexedText || 'last indexed n/a'}</div>
      </div>
    </aside>
  )
}
