import type { Citation } from '../../types/api'

export function citationLabel(c: Citation): string {
  if (c.kind === 'commit') return `commit ${c.commit}`
  const range = c.line_start
    ? `:${c.line_start}${c.line_end && c.line_end !== c.line_start ? `-${c.line_end}` : ''}`
    : ''
  return `${c.path}${range}`
}

type Props = {
  citation: Citation
  block?: boolean
  onClick: (c: Citation) => void
}

export function CitationChip({ citation, block, onClick }: Props) {
  return (
    <button
      className={'cite' + (block ? ' cite-block' : '')}
      onClick={() => onClick(citation)}
    >
      <span className="arrow">▸</span>
      <span>{citationLabel(citation)}</span>
    </button>
  )
}
