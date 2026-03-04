type Props = { page: string; setPage: (v: string) => void }

const GROUPS = [
  {
    label: 'Understand',
    pages: [
      { id: 'atlas', label: 'Atlas' },
      { id: 'architecture', label: 'Architecture' },
      { id: 'impact', label: 'Impact Simulator' },
    ]
  },
  {
    label: 'Operate',
    pages: [
      { id: 'context-builder', label: 'Context Builder' },
    ]
  },
  {
    label: 'Track',
    pages: [
      { id: 'issues', label: 'Issues' },
      { id: 'risks', label: 'Risks' },
      { id: 'decisions', label: 'Decisions' },
      { id: 'changes', label: 'History' },
    ]
  }
]

export function Sidebar({ page, setPage }: Props) {
  return (
    <aside className="sidebar">
      <h1>&gt; copyclip</h1>
      <nav>
        {GROUPS.map((g) => (
          <div key={g.label} className="nav-group">
            <div className="nav-group-label" style={{ fontSize: '0.7rem', textTransform: 'uppercase', opacity: 0.5, marginTop: '1rem', marginBottom: '0.5rem', paddingLeft: '0.5rem' }}>
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
    </aside>
  )
}
