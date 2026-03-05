type Props = { page: string; setPage: (v: string) => void; lastIndexedText?: string }

const GROUPS = [
  {
    label: 'Core',
    pages: [
      { id: 'ask', label: 'consciousness' },
      { id: 'atlas-3d', label: 'atlas' },
      { id: 'timeline', label: 'event timeline' },
      { id: 'planning', label: 'planning' },
    ]
  },
  {
    label: 'Analyze',
    pages: [
      { id: 'architecture', label: 'architecture' },
      { id: 'impact', label: 'impact simulator' },
      { id: 'risks', label: 'risk heatmap' },
    ]
  },
  {
    label: 'System',
    pages: [
      { id: 'context-builder', label: 'context builder' },
      { id: 'decisions', label: 'intent log' },
      { id: 'settings', label: 'settings' },
    ]
  }
]

export function Sidebar({ page, setPage, lastIndexedText }: Props) {
  return (
    <aside className="sidebar">
      <div>
        <h1 style={{ marginBottom: '32px', color: 'var(--text-primary)' }}>
          <span style={{ color: 'var(--accent-cyan)' }}>&gt;</span> copyclip
        </h1>
        
        <nav>
          {GROUPS.map((g) => (
            <div key={g.label} className="nav-group">
              <div className="section-title" style={{ paddingLeft: '10px', marginBottom: '8px', opacity: 0.6 }}>
                {g.label}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {g.pages.map((p) => (
                  <button 
                    key={p.id} 
                    className={page === p.id ? 'active' : ''} 
                    onClick={() => setPage(p.id)}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </div>

      <div style={{ display: 'grid', gap: 12, padding: '0 4px' }}>
        <div className="panel" style={{ padding: '10px', fontSize: 11, color: 'var(--text-tertiary)', background: 'transparent' }}>
          / v0.3.0_stable
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-tertiary)', paddingLeft: '10px' }}>
          {lastIndexedText || 'system ready'}
        </div>
      </div>
    </aside>
  )
}
