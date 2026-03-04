import { useState } from 'react'
import { api } from '../api/client'
import type { AskResponse } from '../types/api'

export function AskPage() {
  const [q, setQ] = useState('What are the highest-risk areas right now?')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AskResponse | null>(null)
  const [error, setError] = useState('')

  const runAsk = async () => {
    if (!q.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await api.ask(q.trim())
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ask failed')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section>
      <h2>ask project</h2>
      <div className="panel" style={{ display: 'grid', gap: 10 }}>
        <textarea value={q} onChange={(e) => setQ(e.target.value)} rows={4} style={{ width: '100%' }} />
        <div>
          <button onClick={runAsk} disabled={loading}>{loading ? 'Asking…' : 'Ask'}</button>
        </div>
        {error && <div className="error">{error}</div>}
        {result && (
          <div style={{ display: 'grid', gap: 8 }}>
            <div><strong>Grounded:</strong> {String(result.grounded)}</div>
            <div>{result.answer}</div>
            <div>
              <strong>Citations</strong>
              <ul>
                {result.citations.map((c, i) => (
                  <li key={`${c.type}-${c.id}-${i}`}>[{c.type}] {c.label}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
