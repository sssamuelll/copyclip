import type { ChangeItem } from '../types/api'

export function ChangesPage({ items }: { items: ChangeItem[] }) {
  return (
    <section>
      <h2>changes</h2>
      <div className="panel"><ul>{items.map((c) => <li key={c.sha}>{c.sha.slice(0, 7)} — {c.message}</li>)}</ul></div>
    </section>
  )
}
