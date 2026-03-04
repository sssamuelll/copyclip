import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api/client'
import { Sidebar } from './components/Sidebar'
import { ArchitecturePage } from './pages/ArchitecturePage'
import { ChangesPage } from './pages/ChangesPage'
import { DecisionsPage } from './pages/DecisionsPage'
import { AtlasPage } from './pages/AtlasPage'
import { RisksPage } from './pages/RisksPage'
import { IssuesPage } from './pages/IssuesPage'
import { ContextBuilderPage } from './pages/ContextBuilderPage'
import { ImpactSimulatorPage } from './pages/ImpactSimulatorPage'
import { AgentTerminal } from './components/AgentTerminal'
import type { ArchEdge, ArchNode, ChangeItem, DecisionItem, IssueItem, Overview, RiskItem } from './types/api'

type Page = 'atlas' | 'architecture' | 'impact' | 'context-builder' | 'changes' | 'decisions' | 'risks' | 'issues'

export function App() {
  const [page, setPage] = useState<Page>('atlas')
  const [overview, setOverview] = useState<Overview>()
  const [changes, setChanges] = useState<ChangeItem[]>([])
  const [decisions, setDecisions] = useState<DecisionItem[]>([])
  const [risks, setRisks] = useState<RiskItem[]>([])
  const [issues, setIssues] = useState<IssueItem[]>([])
  const [nodes, setNodes] = useState<ArchNode[]>([])
  const [edges, setEdges] = useState<ArchEdge[]>([])
  const [error, setError] = useState<string>('')
  const reloadTimer = useRef<number | null>(null)

  const loadAll = useCallback(async () => {
    try {
      const [o, c, d, r, i, a] = await Promise.all([
        api.overview(),
        api.changes(),
        api.decisions(),
        api.risks(),
        api.issues(),
        api.architecture()
      ])
      setOverview(o)
      setChanges(c.items)
      setDecisions(d.items)
      setRisks(r.items)
      setIssues(i.items)
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

  return (
    <div className="app">
      <Sidebar page={page} setPage={(v) => setPage(v as Page)} />
      <main className="main">
        {error && <div className="error">API error: {error}. Make sure `copyclip start` is running.</div>}
        {page === 'atlas' && <AtlasPage overview={overview} changes={changes} risks={risks} decisions={decisions} />}
        {page === 'architecture' && <ArchitecturePage nodes={nodes} edges={edges} />}
        {page === 'impact' && <ImpactSimulatorPage />}
        {page === 'context-builder' && <ContextBuilderPage />}
        {page === 'changes' && <ChangesPage items={changes} />}
        {page === 'decisions' && <DecisionsPage items={decisions} />}
        {page === 'risks' && <RisksPage items={risks} />}
        {page === 'issues' && <IssuesPage items={issues} />}
      </main>
      <AgentTerminal />
    </div>
  )
}
