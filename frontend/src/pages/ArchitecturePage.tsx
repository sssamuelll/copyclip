import type { ArchEdge, ArchNode } from '../types/api'

export function ArchitecturePage({ nodes, edges }: { nodes: ArchNode[]; edges: ArchEdge[] }) {
  return (
    <section>
      <h2>architecture</h2>
      <div className="panel">
        <h3>module edges</h3>
        <ul>
          {edges.slice(0, 30).map((e, i) => (
            <li key={`${e.from}-${e.to}-${i}`}>{e.from} → {e.to}</li>
          ))}
        </ul>
      </div>
      <div className="panel">
        <h3>modules ({nodes.length})</h3>
        <div className="chips">{nodes.map((n) => <span key={n.name} className="chip">{n.name}</span>)}</div>
      </div>
    </section>
  )
}
