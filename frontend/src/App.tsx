import { useState } from 'react'
import { Atlas3DPage } from './pages/Atlas3DPage'
import { HandoffPage } from './pages/HandoffPage'
import { SettingsPage } from './pages/SettingsPage'
import { CuadernoPage } from './pages/CuadernoPage'
import { SURVIVOR_LABELS, type SurvivorPage } from './nav'

import './styles/cuaderno.css'
import './styles/atlas-chrome.css'

type Page = 'cuaderno' | SurvivorPage

// copyclip IS the cuaderno: the full-screen home and the only persistent
// surface (Wave 5 deleted the dashboard shell). The three surviving auxiliary
// views are reached from the cuaderno's ⊞ menu and render full-screen with a
// "back to cuaderno" control.
export function App() {
  const [page, setPage] = useState<Page>('cuaderno')
  const [toast, setToast] = useState('')

  const notify = (msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast(''), 2200)
  }

  if (page === 'cuaderno') {
    return (
      <div style={{ height: '100vh', overflow: 'hidden', background: 'var(--bg)', color: 'var(--text-primary)' }}>
        <CuadernoPage onNavigate={setPage} />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg)', color: 'var(--text-primary)' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          padding: '0 16px',
          height: 44,
          flex: '0 0 auto',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <button className="btn" onClick={() => setPage('cuaderno')} style={{ padding: '5px 12px' }}>
          ← cuaderno
        </button>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)', letterSpacing: '.04em' }}>
          {SURVIVOR_LABELS[page]}
        </span>
      </header>

      <main style={{ flex: 1, overflowY: 'auto', position: 'relative', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: 24, flex: 1 }}>
          {page === 'atlas-3d' && <Atlas3DPage />}
          {page === 'handoff' && <HandoffPage onNotify={notify} />}
          {page === 'settings' && <SettingsPage onNotify={notify} />}
        </div>
      </main>

      {toast && (
        <div
          style={{
            position: 'fixed',
            top: 24,
            left: '50%',
            transform: 'translateX(-50%)',
            background: 'var(--accent-cyan)',
            color: '#000',
            borderRadius: 4,
            padding: '8px 16px',
            zIndex: 9999,
            fontWeight: 500,
          }}
        >
          {toast}
        </div>
      )}
    </div>
  )
}
