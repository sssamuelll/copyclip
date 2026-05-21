type Props = { page: string; setPage: (v: string) => void; lastIndexedText?: string }

const GROUPS = [
  {
    label: 'Project Memory',
    pages: [
      { id: 'reacquaintance', label: 'catch me up' },
      { id: 'ask', label: 'ask project' },
      { id: 'handoff', label: 'safe handoff' },
      { id: 'debt-navigator', label: 'debt navigator' },
      { id: 'atlas-3d', label: 'codebase map' },
      { id: 'timeline', label: 'project timeline' },
      { id: 'planning', label: 'intent field' },
    ]
  },
  {
    label: 'Structures',
    pages: [
      { id: 'changes', label: 'change field' },
      { id: 'architecture', label: 'structure graph' },
      { id: 'impact', label: 'propagation oracle' },
      { id: 'risks', label: 'distortion field' },
    ]
  },
  {
    label: 'Bridges',
    pages: [
      { id: 'context-builder', label: 'context forge' },
      { id: 'decisions', label: 'decision history' },
      { id: 'settings', label: 'nexus' },
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
          / v0.4.0_stable
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-tertiary)', paddingLeft: '10px' }}>
          {lastIndexedText || 'project memory active'}
        </div>
      </div>
    </aside>
  )
}
