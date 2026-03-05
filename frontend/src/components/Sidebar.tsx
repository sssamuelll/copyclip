type Props = { page: string; setPage: (v: string) => void; lastIndexedText?: string }

const GROUPS = [
  {
    label: 'Core',
    pages: [
      { id: 'ask', label: 'consciousness', icon: '🧠' },
      { id: 'atlas-3d', label: 'atlas 3d', icon: '🌐' },
      { id: 'timeline', label: 'event timeline', icon: '⏳' },
      { id: 'planning', label: 'planning', icon: '📋' },
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
    <aside className="sidebar" style={{ background: '#050505', borderRight: '1px solid #1a1a1a' }}>
      <div>
        <div style={{ padding: '0 8px 24px 8px' }}>
          <h1 style={{ fontSize: '1.2rem', letterSpacing: '-0.5px' }}>
            <span style={{ color: 'var(--accent-cyan)' }}>&gt;</span> copyclip
          </h1>
        </div>
        
        <nav>
          {GROUPS.map((g) => (
            <div key={g.label} className="nav-group" style={{ marginBottom: '24px' }}>
              <div style={{ fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase', color: '#444', marginBottom: '8px', paddingLeft: '12px', letterSpacing: '1px' }}>
                {g.label}
              </div>
              {g.pages.map((p) => (
                <button 
                  key={p.id} 
                  className={page === p.id ? 'active' : ''} 
                  onClick={() => setPage(p.id)}
                  style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '10px',
                    padding: '10px 12px',
                    fontSize: '0.85rem',
                    borderRadius: '6px',
                    margin: '2px 4px',
                    border: 'none',
                    background: page === p.id ? 'rgba(6, 182, 212, 0.1)' : 'transparent',
                    color: page === p.id ? 'var(--accent-cyan)' : '#888'
                  }}
                >
                  <span style={{ fontSize: '1rem' }}>{(p as any).icon || '•'}</span>
                  {p.label}
                </button>
              ))}
            </div>
          ))}
        </nav>
      </div>

      <div style={{ padding: '16px' }}>
        <div className="muted" style={{ fontSize: '0.65rem', marginBottom: '4px' }}>VERSION 0.3.0</div>
        <div style={{ fontSize: '0.65rem', color: '#555' }}>{lastIndexedText || 'ready'}</div>
      </div>
    </aside>
  )
}
