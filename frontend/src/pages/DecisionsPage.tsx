import type { DecisionItem } from '../types/api'

export function DecisionsPage({ items }: { items: DecisionItem[] }) {
  return (
    <section>
      <h2>decisions</h2>
      <div className="panel"><ul>{items.map((d) => <li key={d.id}>#{d.id} [{d.status}] {d.title}</li>)}</ul></div>
    </section>
  )
}
