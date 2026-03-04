import type { ChangeItem } from '../types/api'

export function ChangesPage({ items, focusCommitId }: { items: ChangeItem[]; focusCommitId?: string | null }) {
  return (
    <section>
      <h2>changes</h2>
      <div className="panel"><ul>{items.map((c) => {
        const focused = !!focusCommitId && c.sha.startsWith(focusCommitId)
        return <li key={c.sha} style={focused ? { background: 'rgba(16,185,129,0.2)', padding: '2px 4px' } : undefined}>{c.sha.slice(0, 7)} — {c.message}</li>
      })}</ul></div>
    </section>
  )
}
