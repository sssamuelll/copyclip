import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { FileItem, ImpactResult } from '../types/api'

export function ImpactSimulatorPage() {
  const [files, setFiles] = useState<FileItem[]>([])
  const [search, setSearch] = useState('')
  const [impact, setImpact] = useState<ImpactResult | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.files().then(res => setFiles(res.items))
  }, [])

  const analyzeImpact = async (path: string) => {
    setLoading(true)
    try {
      const res = await api.impact(path)
      setImpact(res)
    } finally {
      setLoading(false)
    }
  }

  const filtered = files.filter(f => f.path.toLowerCase().includes(search.toLowerCase())).slice(0, 10)

  return (
    <section className="page">
      <h2>Impact Simulator</h2>
      <p className="muted" style={{ marginBottom: '2rem' }}>
        Select a file to visualize its blast radius (dependents) across the project modules.
      </p>
      
      <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '2rem' }}>
        <div className="panel">
          <h3>Select File</h3>
          <input 
            type="text" 
            placeholder="Search files..." 
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ width: '100%', background: '#000', color: '#fff', border: '1px solid var(--border)', padding: '8px', margin: '1rem 0' }}
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {filtered.map(f => (
              <button 
                key={f.path} 
                onClick={() => analyzeImpact(f.path)}
                className="btn"
                style={{ fontSize: '0.8rem', textAlign: 'left' }}
              >
                {f.path.split('/').pop()}
              </button>
            ))}
          </div>
        </div>

        <div className="panel" style={{ minHeight: '400px', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {!impact && !loading && <div className="muted" style={{ margin: 'auto' }}>Select a file to start simulation</div>}
          {loading && <div className="muted" style={{ margin: 'auto' }}>Calculating blast radius...</div>}
          
          {impact && (
            <>
              <div>
                <div className="muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase' }}>Target Module</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--accent)' }}>{impact.target_module}</div>
              </div>

              <div>
                <div className="muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Impacted Dependents (Blast Radius)</div>
                {impact.impacted_modules.length === 0 ? (
                  <div className="muted">No direct dependents found. Low risk of systemic breakage.</div>
                ) : (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                    {impact.impacted_modules.map(m => (
                      <div key={m} className="card" style={{ border: '1px solid #7f1d1d', background: '#2a1111', color: '#fecaca' }}>
                        {m}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              
              <div className="panel" style={{ border: '1px solid #92400e', background: 'rgba(146, 64, 14, 0.1)' }}>
                <span style={{ fontWeight: 'bold', color: '#fbbf24' }}>AI Advisory:</span>
                <p style={{ margin: '8px 0 0 0', fontSize: '0.9rem' }}>
                  Modifying {impact.target_module} may require regression testing in {impact.impacted_modules.length} other areas. 
                  Consider checking the interfaces of the affected modules.
                </p>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
