import { useEffect, useState } from 'react'
import { api } from './api/client'
import { Sidebar } from './components/Sidebar'
import { ArchitecturePage } from './pages/ArchitecturePage'
import { ChangesPage } from './pages/ChangesPage'
import { DecisionsPage } from './pages/DecisionsPage'
import { OverviewPage } from './pages/OverviewPage'
import { RisksPage } from './pages/RisksPage'
import type { ArchEdge, ArchNode, ChangeItem, DecisionItem, Overview, RiskItem } from './types/api'

type Page = 'overview' | 'architecture' | 'changes' | 'decisions' | 'risks'

export function App() {
  const [page, setPage] = useState<Page>('overview')
  const [overview, setOverview] = useState<Overview>()
  const [changes, setChanges] = useState<ChangeItem[]>([])
  const [decisions, setDecisions] = useState<DecisionItem[]>([])
  const [risks, setRisks] = useState<RiskItem[]>([])
  const [nodes, setNodes] = useState<ArchNode[]>([])
  const [edges, setEdges] = useState<ArchEdge[]>([])
  const [error, setError] = useState<string>('')

  useEffect(() => {
    ;(async () => {
      try {
        const [o, c, d, r, a] = await Promise.all([
          api.overview(),
          api.changes(),
          api.decisions(),
          api.risks(),
          api.architecture()
        ])
        setOverview(o)
        setChanges(c.items)
        setDecisions(d.items)
        setRisks(r.items)
        setNodes(a.nodes)
        setEdges(a.edges)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load API data')
      }
    })()
  }, [])

  return (
    <div className="app">
      <Sidebar page={page} setPage={(v) => setPage(v as Page)} />
      <main className="main">
        {error && <div className="error">API error: {error}. Make sure `copyclip serve --path . --port 4310` is running.</div>}
        {page === 'overview' && <OverviewPage overview={overview} changes={changes} risks={risks} decisions={decisions} />}
        {page === 'architecture' && <ArchitecturePage nodes={nodes} edges={edges} />}
        {page === 'changes' && <ChangesPage items={changes} />}
        {page === 'decisions' && <DecisionsPage items={decisions} />}
        {page === 'risks' && <RisksPage items={risks} />}
      </main>
    </div>
  )
}
