import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import { Sidebar } from './components/Sidebar'
import { ReacquaintancePage } from './pages/ReacquaintancePage'
import { AskPage } from './pages/AskPage'
import { ArchitecturePage } from './pages/ArchitecturePage'
import { RisksPage } from './pages/RisksPage'
import { ContextBuilderPage } from './pages/ContextBuilderPage'
import { DecisionsPage } from './pages/DecisionsPage'
import { SettingsPage } from './pages/SettingsPage'
import { ImpactSimulatorPage } from './pages/ImpactSimulatorPage'
import { ChangesPage } from './pages/ChangesPage'

import { Atlas3DPage } from './pages/Atlas3DPage'
import { TimelinePage } from './pages/TimelinePage'
import { PlanningPage } from './pages/PlanningPage'

import type { ArchEdge, ArchNode, ChangeItem, DecisionItem, Overview, RiskItem } from './types/api'

type Page = 'reacquaintance' | 'ask' | 'atlas-3d' | 'timeline' | 'planning' | 'changes' | 'architecture' | 'impact' | 'risks' | 'context-builder' | 'decisions' | 'settings'

export function App() {
  const [page, setPage] = useState<Page>('reacquaintance')
  const [overview, setOverview] = useState<Overview>()
  const [decisions, setDecisions] = useState<DecisionItem[]>([])
  const [risks, setRisks] = useState<RiskItem[]>([])
  const [changes, setChanges] = useState<ChangeItem[]>([])
  const [nodes, setNodes] = useState<ArchNode[]>([])
  const [edges, setEdges] = useState<ArchEdge[]>([])
  const [error, setError] = useState<string>('')
  const [toast, setToast] = useState<string>('')
  const [focusDecisionId, setFocusDecisionId] = useState<number | null>(null)
  const [focusRiskArea, setFocusRiskArea] = useState<string | null>(null)
  const [focusCommitId, setFocusCommitId] = useState<string | null>(null)
  const [focusFilePath, setFocusFilePath] = useState<string | null>(null)
  const reloadTimer = useRef<number | null>(null)

  const loadAll = useCallback(async () => {
    try {
      const [o, d, r, c, a] = await Promise.all([
        api.overview(),
        api.decisions(),
        api.risks(),
        api.changes(),
        api.architecture()
      ])
      setOverview(o)
      setDecisions(d.items)
      setRisks(r.items)
      setChanges(c.items)
      setNodes(a.nodes)
      setEdges(a.edges)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load API data')
    }
  }, [])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  const notify = (msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast(''), 2200)
  }

  const openDecision = (id: number) => {
    setFocusDecisionId(id)
    setPage('decisions')
  }

  const openRisk = (area: string) => {
    setFocusRiskArea(area)
    setPage('risks')
  }

  const openChanges = (opts?: { commitId?: string | null; filePath?: string | null }) => {
    setFocusCommitId(opts?.commitId || null)
    setFocusFilePath(opts?.filePath || null)
    setPage('changes')
  }

  return (
    <div className="app gen-ui-layout" style={{ display: 'flex', height: '100vh', background: 'var(--bg)', color: 'var(--text-primary)' }}>
      
      <Sidebar 
        page={page} 
        setPage={(v) => setPage(v as Page)} 
        lastIndexedText={overview?.meta?.generated_at ? `last indexed ${overview.meta.generated_at.replace('T', ' ').slice(0, 16)}` : 'ready'}
      />

      <main style={{ flex: 1, overflowY: 'auto', position: 'relative', display: 'flex', flexDirection: 'column' }}>
        
        {/* Top Indicator Persistent */}
        <div style={{ position: 'absolute', top: 12, right: 24, zIndex: 10, display: 'flex', gap: 12 }}>
           {error && <span className="badge badge-high">CONSCIOUSNESS OFFLINE</span>}
           <span className="badge badge-low">{page.replace('-', ' ')} field</span>
        </div>

        <div style={{ padding: '24px', flex: 1 }}>
          {page === 'reacquaintance' && <ReacquaintancePage onOpenDecision={openDecision} onOpenRisk={openRisk} onOpenChanges={openChanges} />}
          {page === 'ask' && <AskPage onNotify={notify} onOpenDecision={openDecision} onOpenRisk={openRisk} onOpenChanges={openChanges} />}
          {page === 'atlas-3d' && <Atlas3DPage />}
          {page === 'timeline' && <TimelinePage />}
          {page === 'planning' && <PlanningPage />}
          {page === 'changes' && <ChangesPage items={changes} risks={risks} focusCommitId={focusCommitId} focusFilePath={focusFilePath} onOpenDecision={openDecision} onOpenRisk={openRisk} />}
          {page === 'architecture' && <ArchitecturePage nodes={nodes} edges={edges} />}
          {page === 'impact' && <ImpactSimulatorPage />}
          {page === 'risks' && <RisksPage items={risks} focusRiskArea={focusRiskArea} />}
          {page === 'context-builder' && <ContextBuilderPage />}
          {page === 'decisions' && <DecisionsPage items={decisions} focusDecisionId={focusDecisionId} />}
          {page === 'settings' && <SettingsPage onNotify={notify} />}
        </div>
      </main>

      {/* Global Toast */}
      {toast && (
        <div style={{ position: 'fixed', top: 24, left: '50%', transform: 'translateX(-50%)', background: 'var(--accent-cyan)', color: '#000', borderRadius: 4, padding: '8px 16px', zIndex: 9999, fontWeight: 500 }}>
          {toast}
        </div>
      )}
    </div>
  )
}
