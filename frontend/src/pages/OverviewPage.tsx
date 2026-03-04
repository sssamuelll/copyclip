import type { ChangeItem, DecisionItem, Overview, RiskItem } from '../types/api'

type Props = {
  overview?: Overview
  changes: ChangeItem[]
  risks: RiskItem[]
  decisions: DecisionItem[]
}

export function OverviewPage({ overview, changes, risks, decisions }: Props) {
  return (
    <section>
      <h2>overview</h2>
      <div className="kpis">
        <Card label="files" value={overview?.files ?? 0} />
        <Card label="commits" value={overview?.commits ?? 0} />
        <Card label="modules" value={overview?.modules ?? 0} />
        <Card label="risks" value={overview?.risks ?? 0} />
        <Card label="decisions" value={overview?.decisions ?? 0} />
        <Card label="issues" value={overview?.issues ?? 0} />
      </div>
      <div className="cols">
        <Panel title="recent changes" items={changes.slice(0, 8).map((c) => `${c.sha.slice(0, 7)} — ${c.message}`)} />
        <Panel title="top risks" items={risks.slice(0, 8).map((r) => `[${r.severity}] ${r.area} (${r.score})`)} />
        <Panel title="open decisions" items={decisions.slice(0, 8).map((d) => `#${d.id} [${d.status}] ${d.title}`)} />
      </div>
    </section>
  )
}

function Card({ label, value }: { label: string; value: number }) {
  return (
    <div className="card">
      <div className="muted">{label}</div>
      <div className="value">{value}</div>
    </div>
  )
}

function Panel({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="panel">
      <h3>{title}</h3>
      <ul>{items.length ? items.map((i) => <li key={i}>{i}</li>) : <li className="muted">No data</li>}</ul>
    </div>
  )
}
