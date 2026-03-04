type Props = { page: string; setPage: (v: string) => void }
const pages = ['overview', 'architecture', 'changes', 'decisions', 'risks'] as const

export function Sidebar({ page, setPage }: Props) {
  return (
    <aside className="sidebar">
      <h1>&gt; copyclip</h1>
      <nav>
        {pages.map((p) => (
          <button key={p} className={page === p ? 'active' : ''} onClick={() => setPage(p)}>
            {p}
          </button>
        ))}
      </nav>
    </aside>
  )
}
