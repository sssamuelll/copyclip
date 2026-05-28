import type { CallersTreeWidget, Citation } from '../../../types/api'

type Props = {
  widget: CallersTreeWidget
  onOpenCitation: (c: Citation) => void
}

function citationLabel(c: Citation): string {
  if (c.kind === 'commit') return `commit ${c.commit}`
  const range = c.line_start
    ? `:${c.line_start}${c.line_end && c.line_end !== c.line_start ? `-${c.line_end}` : ''}`
    : ''
  return `${c.path}${range}`
}

export function CallersTree({ widget, onOpenCitation }: Props) {
  return (
    <div className="widget">
      <div className="widget-head">
        <span>
          <span className="kind">widget</span> · callers
        </span>
        <span>{`${widget.callers.length} sites`}</span>
      </div>
      <div className="widget-body tree">
        <div className="node">
          <span className="glyph">◇</span>
          <span className="name">{widget.root}</span>
        </div>
        {widget.callers.map((c, i) => (
          <div className="node indent" key={i}>
            <span className="glyph">└─</span>
            <button className="cite" onClick={() => onOpenCitation(c.citation)}>
              <span className="arrow">▸</span>
              <span>{citationLabel(c.citation)}</span>
            </button>
            {c.note ? (
              <span style={{ color: 'var(--ink-3)', marginLeft: 4 }}>{c.note}</span>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  )
}
