import { useEffect, useState } from 'react'
import type { Citation } from '../../types/api'

type Props = {
  citation: Citation
  onClose: () => void
}

type FileSlice = {
  path: string
  lines: { n: number; text: string }[]
  blame?: { commit: string; author: string; when: string }
}

async function fetchFileSlice(c: Citation): Promise<FileSlice | null> {
  if (c.kind === 'commit') return null
  const params = new URLSearchParams({ path: c.path })
  if (c.line_start) params.set('line_start', String(c.line_start))
  if (c.line_end) params.set('line_end', String(c.line_end))
  const r = await fetch(`/api/cuaderno/file?${params.toString()}`)
  if (!r.ok) return null
  return await r.json()
}

export function SidePanel({ citation, onClose }: Props) {
  const [slice, setSlice] = useState<FileSlice | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    setLoading(true)
    fetchFileSlice(citation)
      .then(setSlice)
      .finally(() => setLoading(false))
  }, [citation])

  if (citation.kind === 'commit') {
    return (
      <>
        <div className="sidepanel-backdrop" onClick={onClose} />
        <div className="sidepanel">
          <div className="sidepanel-head">
            <div className="path">
              <span className="dim">commit</span>
              <span>{citation.commit}</span>
            </div>
            <button className="close" onClick={onClose}>esc</button>
          </div>
          <div className="sidepanel-body" style={{ padding: 24 }}>
            <p style={{ color: 'var(--ink-3)' }}>
              Commit detail view coming in Phase 1.5. For now, this confirms
              the citation: <code>{citation.commit}</code>.
            </p>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <div className="sidepanel-backdrop" onClick={onClose} />
      <div className="sidepanel">
        <div className="sidepanel-head">
          <div className="path">
            <span className="dim">▸</span>
            <span>{citation.path}</span>
            {citation.line_start ? (
              <span className="dim">
                :{citation.line_start}
                {citation.line_end && citation.line_end !== citation.line_start
                  ? `-${citation.line_end}`
                  : ''}
              </span>
            ) : null}
          </div>
          <button className="close" onClick={onClose}>esc</button>
        </div>
        <div className="sidepanel-body">
          {loading ? (
            <div style={{ padding: 24, color: 'var(--ink-3)' }}>loading…</div>
          ) : !slice ? (
            <div style={{ padding: 24, color: 'var(--ink-3)' }}>
              could not load file.
            </div>
          ) : (
            <div className="file-code">
              {slice.lines.map((r) => (
                <div
                  key={r.n}
                  className={
                    'row' +
                    (citation.line_start &&
                    r.n >= citation.line_start &&
                    r.n <= (citation.line_end ?? citation.line_start)
                      ? ' hi'
                      : '')
                  }
                >
                  <div className="lno">{r.n}</div>
                  <div>{r.text || ' '}</div>
                </div>
              ))}
            </div>
          )}
        </div>
        {slice?.blame ? (
          <div className="sidepanel-meta">
            <span className="pair">
              <b>blame </b>
              {slice.blame.commit}
            </span>
            <span className="pair">
              <b>by </b>
              {slice.blame.author}
            </span>
            <span className="pair">
              <b>on </b>
              {slice.blame.when}
            </span>
          </div>
        ) : null}
      </div>
    </>
  )
}
