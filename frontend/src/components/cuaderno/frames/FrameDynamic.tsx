import type { Block, Citation, Frame } from '../../../types/api'
import { CitationChip } from '../CitationChip'

const STATUS_BANNER: Partial<Record<NonNullable<Frame['status']>, { kicker: string; text: string }>> = {
  ungrounded: {
    kicker: 'not grounded',
    text: 'This answer was not anchored to the code — the tutor answered without reading enough evidence. Re-ask, or rephrase to point at a specific file, function, or commit.',
  },
  insufficient_evidence: {
    kicker: 'insufficient evidence',
    text: 'The tutor looked but the project does not contain enough to answer this confidently. What it would need is named above.',
  },
  partial: {
    kicker: 'partial answer',
    text: 'This answer was interrupted before it finished. It may be incomplete.',
  },
  fallback: {
    kicker: 'no answer',
    text: 'The tutor could not produce an answer for this question this time.',
  },
}
import { GraphSubset } from '../widgets/GraphSubset'
import { SequenceDiagram } from '../widgets/SequenceDiagram'
import { CallersTree } from '../widgets/CallersTree'

type Props = {
  frame: Frame
  onOpenCitation: (c: Citation) => void
  onAsk: (question: string) => void
}

export function FrameDynamic({ frame, onOpenCitation, onAsk }: Props) {
  const banner = frame.status ? STATUS_BANNER[frame.status] : undefined
  return (
    <>
      <div className="cua-question">
        <span className="label">you asked</span>
        <span className="q">{frame.question}</span>
      </div>
      {banner ? (
        <div className="callout" role="status">
          <div className="kicker">{banner.kicker}</div>
          <p>{banner.text}</p>
        </div>
      ) : null}
      {frame.blocks.map((b, i) => (
        <BlockRender
          key={i}
          block={b}
          onOpenCitation={onOpenCitation}
          onAsk={onAsk}
        />
      ))}
    </>
  )
}

function BlockRender({
  block,
  onOpenCitation,
  onAsk,
}: {
  block: Block
  onOpenCitation: (c: Citation) => void
  onAsk: (question: string) => void
}) {
  switch (block.kind) {
    case 'lead':
      return <p className="cua-lead">{block.text}</p>
    case 'paragraph':
      return <p className="cua-p">{block.text}</p>
    case 'ordered_list':
      return (
        <ol className="cua-list">
          {block.items.map((item, i) => (
            <li key={i}>
              <div>
                <div className="head">{item.head}</div>
                <div className="desc">{item.desc}</div>
                {item.citation ? (
                  <CitationChip citation={item.citation} block onClick={onOpenCitation} />
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      )
    case 'code_block':
      return (
        <>
          {block.citation ? (
            <CitationChip citation={block.citation} block onClick={onOpenCitation} />
          ) : null}
          <pre className="code">
            {block.code.split('\n').map((l, i) => (
              <span className="ln" key={i}>
                {l || ' '}
                {'\n'}
              </span>
            ))}
          </pre>
        </>
      )
    case 'ascii_block':
      return <pre className="ascii">{block.text}</pre>
    case 'citation':
      return <CitationChip citation={block.citation} block onClick={onOpenCitation} />
    case 'citation_stack':
      return (
        <div className="cite-stack">
          {block.items.map((it, i) => (
            <a key={i} onClick={() => onOpenCitation(it.citation)}>
              <span className="arrow">▸</span>
              <span>
                {it.citation.kind === 'commit'
                  ? `commit ${it.citation.commit}`
                  : `${it.citation.path}${
                      it.citation.line_start
                        ? `:${it.citation.line_start}${
                            it.citation.line_end && it.citation.line_end !== it.citation.line_start
                              ? `-${it.citation.line_end}`
                              : ''
                          }`
                        : ''
                    }`}
              </span>
              {it.note ? (
                <span style={{ color: 'var(--ink-3)' }}>  {it.note}</span>
              ) : null}
            </a>
          ))}
        </div>
      )
    case 'callout':
      return (
        <div className="callout">
          <div className="kicker">{block.kicker}</div>
          <p>{block.text}</p>
          {block.citations
            ? block.citations.map((c, i) => (
                <div key={i} style={{ marginTop: i === 0 ? 8 : 4 }}>
                  <CitationChip citation={c} onClick={onOpenCitation} />
                </div>
              ))
            : null}
        </div>
      )
    case 'widget':
      switch (block.widget.kind) {
        case 'graph_subset':
          return <GraphSubset widget={block.widget} />
        case 'sequence_diagram':
          return <SequenceDiagram widget={block.widget} />
        case 'callers_tree':
          return (
            <CallersTree widget={block.widget} onOpenCitation={onOpenCitation} />
          )
      }
      return null
    case 'followups':
      return (
        <div className="followups">
          <div className="cap">go deeper</div>
          <div className="btns">
            {block.items.map((it, i) => (
              <button key={i} className="fu" onClick={() => onAsk(it.question)}>
                <span className="arr">↳</span> {it.label}
              </button>
            ))}
          </div>
        </div>
      )
  }
}
