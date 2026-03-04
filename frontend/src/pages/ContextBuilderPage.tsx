import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { FileItem, IssueItem } from '../types/api'

export function ContextBuilderPage() {
  const [files, setFiles] = useState<FileItem[]>([])
  const [issues, setIssues] = useState<IssueItem[]>([])
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set())
  const [selectedIssues, setSelectedIssues] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [includeDecisions, setIncludeDecisions] = useState(true)
  const [minimize, setMinimize] = useState<'basic' | 'aggressive' | 'structural'>('basic')
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [warnings, setWarnings] = useState<string[]>([])

  useEffect(() => {
    api.files().then(res => setFiles(res.items))
    api.issues().then(res => setIssues(res.items))
  }, [])

  const filteredFiles = files.filter(f => f.path.toLowerCase().includes(search.toLowerCase()))

  const toggleFile = (path: string) => {
    const next = new Set(selectedFiles)
    if (next.has(path)) next.delete(path)
    else next.add(path)
    setSelectedFiles(next)
    setWarnings([]) // Reset warnings on change
  }

  const toggleIssue = (id: string) => {
    const next = new Set(selectedIssues)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIssues(next)
    setWarnings([]) // Reset warnings on change
  }

  const handleCopy = async () => {
    setLoading(true)
    setWarnings([])
    try {
      const res = await api.assembleContext({
        files: Array.from(selectedFiles),
        issues: Array.from(selectedIssues),
        include_decisions: includeDecisions,
        minimize
      })
      await navigator.clipboard.writeText(res.context)
      if (res.warnings && res.warnings.length > 0) {
        setWarnings(res.warnings)
      } else {
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      }
    } catch (e) {
      alert('Failed to assemble context')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="page">
      <h2>Context Builder</h2>
      <p className="muted" style={{ marginBottom: '2rem' }}>
        Visually assemble your AI prompt. Select files, issues, and decisions to build the perfect context payload.
      </p>
      
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '2rem' }}>
        <div className="panel" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', maxHeight: '70vh', overflow: 'hidden' }}>
          <h3>Available Context</h3>
          <input 
            type="text" 
            placeholder="Search files..." 
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ background: '#000', border: '1px solid var(--border)', color: '#fff', padding: '8px', width: '100%' }}
          />
          
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <div style={{ marginBottom: '1rem' }}>
              <div className="muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Files</div>
              {filteredFiles.slice(0, 50).map(f => (
                <div key={f.path} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0' }}>
                  <input type="checkbox" checked={selectedFiles.has(f.path)} onChange={() => toggleFile(f.path)} />
                  <span style={{ fontSize: '0.9rem', opacity: selectedFiles.has(f.path) ? 1 : 0.7 }}>{f.path}</span>
                </div>
              ))}
              {filteredFiles.length > 50 && <div className="muted" style={{ fontSize: '0.7rem' }}>+ {filteredFiles.length - 50} more files</div>}
            </div>

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
              <div className="muted" style={{ fontSize: '0.7rem', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Issues</div>
              {issues.map(i => (
                <div key={i.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 0' }}>
                  <input type="checkbox" checked={selectedIssues.has(i.id)} onChange={() => toggleIssue(i.id)} />
                  <span style={{ fontSize: '0.9rem', opacity: selectedIssues.has(i.id) ? 1 : 0.7 }}>#{i.id} {i.title}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        
        <div className="panel" style={{ border: '1px solid var(--accent)', background: 'rgba(16, 185, 129, 0.02)', display: 'flex', flexDirection: 'column' }}>
          <h3>Your Payload</h3>
          <div style={{ flex: 1, overflowY: 'auto', padding: '1rem' }}>
            {selectedFiles.size === 0 && selectedIssues.size === 0 && (
              <div className="muted" style={{ textAlign: 'center', marginTop: '2rem' }}>No items selected</div>
            )}
            {Array.from(selectedFiles).map(f => (
              <div key={f} style={{ fontSize: '0.8rem', padding: '2px 0', display: 'flex', justifyContent: 'space-between' }}>
                <span>{f}</span>
                <button onClick={() => toggleFile(f)} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>×</button>
              </div>
            ))}
            {Array.from(selectedIssues).map(id => (
              <div key={id} style={{ fontSize: '0.8rem', padding: '2px 0', color: 'var(--accent)', display: 'flex', justifyContent: 'space-between' }}>
                <span>Issue #{id}</span>
                <button onClick={() => toggleIssue(id)} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>×</button>
              </div>
            ))}
          </div>

          <div style={{ padding: '1rem', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', gap: '1rem', fontSize: '0.8rem' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <input type="checkbox" checked={includeDecisions} onChange={e => setIncludeDecisions(e.target.checked)} />
                Include Rules
              </label>
              <select 
                value={minimize} 
                onChange={e => setMinimize(e.target.value as any)}
                style={{ background: '#000', color: '#fff', border: '1px solid var(--border)' }}
              >
                <option value="basic">Basic Minimization</option>
                <option value="aggressive">Aggressive</option>
                <option value="structural">Structural</option>
              </select>
            </div>

            {warnings.length > 0 && (
              <div className="panel" style={{ border: '1px solid #92400e', background: 'rgba(146, 64, 14, 0.2)', padding: '8px', fontSize: '0.8rem' }}>
                <div style={{ color: '#fbbf24', fontWeight: 'bold', marginBottom: '4px' }}>Decision Advisor Warning:</div>
                {warnings.map((w, idx) => <div key={idx}>{w}</div>)}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', opacity: 0.7 }}>
                {selectedFiles.size} files, {selectedIssues.size} issues
              </span>
              <button 
                className="btn primary" 
                onClick={handleCopy} 
                disabled={loading || (selectedFiles.size === 0 && selectedIssues.size === 0)}
              >
                {loading ? 'Assembling...' : copied ? 'COPIED!' : 'Copy Context'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
