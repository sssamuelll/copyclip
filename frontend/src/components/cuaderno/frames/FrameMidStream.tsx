import type { ToolRow } from '../../../types/api'
import { renderInline } from '../inline'
import { t } from '../strings'

type Props = {
  question: string
  tools: ToolRow[]
  partial: string
  language?: string | null
}

export function FrameMidStream({ question, tools, partial, language }: Props) {
  return (
    <>
      <div className="cua-question">
        <span className="label">{t('you_asked', language)}</span>
        <span className="q">{question}</span>
      </div>
      <div className="toolcalls" aria-label="LLM tool calls">
        {tools.map((t_, i) => (
          <div key={i} className={`row ${t_.state}`}>
            <span className="tag">
              {t_.state === 'done' ? '✓' : t_.state === 'error' ? '⨯' : t_.state === 'running' ? '◐' : '·'}
            </span>
            <span className="name">{t_.name}</span>
            <span className="args">{t_.args}</span>
            <span className="meta">
              {t_.state === 'done'
                ? `${t_.ms ?? 0} ms`
                : t_.state === 'error'
                ? 'failed'
                : t_.state === 'running'
                ? t('running', language)
                : 'queued'}
            </span>
          </div>
        ))}
      </div>
      <p className="cua-lead">
        {renderInline(partial)}
        <span className="streaming-caret" />
      </p>
    </>
  )
}
