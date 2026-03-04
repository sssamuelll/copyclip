import type { RiskItem } from '../types/api'

export function RisksPage({ items }: { items: RiskItem[] }) {
  return (
    <section>
      <h2>risks</h2>
      <div className="panel"><ul>{items.map((r, i) => <li key={i}>[{r.severity}] {r.area} — {r.rationale} ({r.score})</li>)}</ul></div>
    </section>
  )
}
