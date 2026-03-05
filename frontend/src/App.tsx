import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import { AskPage } from './pages/AskPage'
import type { Overview } from './types/api'

export function App() {
  const [overview, setOverview] = useState<Overview>()
  const [error, setError] = useState<string>('')
  const [toast, setToast] = useState<string>('')
  const reloadTimer = useRef<number | null>(null)

  const loadAll = useCallback(async () => {
    try {
      const o = await api.overview()
      setOverview(o)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load API data')
    }
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  useEffect(() => {
    const sse = new EventSource('/api/events?cursor=0')
    const scheduleReload = () => {
      if (reloadTimer.current) window.clearTimeout(reloadTimer.current)
      reloadTimer.current = window.setTimeout(() => {
        loadAll()
      }, 300)
    }

    sse.addEventListener('decision.created', scheduleReload)
    sse.addEventListener('decision.status_changed', scheduleReload)
    sse.addEventListener('decision.ref_added', scheduleReload)

    return () => {
      if (reloadTimer.current) window.clearTimeout(reloadTimer.current)
      sse.close()
    }
  }, [loadAll])

  const notify = (msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast(''), 2200)
  }

  return (
    <div className="app gen-ui-layout" style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg)', color: 'var(--text-primary)' }}>
      {/* Header Minimalista */}
      <header style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <strong style={{ fontSize: 18, color: 'var(--text-primary)' }}>&gt; copyclip</strong>
          <span className="badge badge-low" style={{ fontFamily: 'monospace' }}>consciousness</span>
        </div>
        <div className="muted" style={{ fontSize: 11 }}>
          {overview?.meta?.generated_at ? `last analyzed: ${overview.meta.generated_at.replace('T', ' ').slice(0, 19)}` : 'analyzing...'}
        </div>
      </header>

      {/* Main Chat Area */}
      <main style={{ flex: 1, overflowY: 'auto', display: 'flex', justifyContent: 'center' }}>
        <div style={{ width: '100%', maxWidth: '900px', padding: '24px' }}>
          {error && <div className="error" style={{ marginBottom: 20 }}>API error: {error}. Make sure `copyclip start` is running.</div>}
          <AskPage onNotify={notify} />
        </div>
      </main>

      {/* Global Toast */}
      {toast && (
        <div style={{ position: 'fixed', top: 24, left: '50%', transform: 'translateX(-50%)', background: 'var(--accent-cyan)', color: '#000', borderRadius: 4, padding: '8px 16px', zIndex: 9999, fontWeight: 500, boxShadow: '0 4px 12px rgba(0,0,0,0.5)' }}>
          {toast}
        </div>
      )}
    </div>
  )
}
