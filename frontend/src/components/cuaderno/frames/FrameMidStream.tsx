type ToolState = 'queued' | 'running' | 'done'

type ToolRow = {
  state: ToolState
  name: string
  args: string
  ms: number | null
}

type Props = {
  question: string
  tools: ToolRow[]
  partial: string
}

export function FrameMidStream({ question, tools, partial }: Props) {
  return (
    <>
      <div className="cua-question">
        <span className="label">you asked</span>
        <span className="q">{question}</span>
      </div>
      <div className="toolcalls" aria-label="LLM tool calls">
        {tools.map((t, i) => (
          <div key={i} className={`row ${t.state}`}>
            <span className="tag">
              {t.state === 'done' ? '✓' : t.state === 'running' ? '◐' : '·'}
            </span>
            <span className="name">{t.name}</span>
            <span className="args">{t.args}</span>
            <span className="meta">
              {t.state === 'done'
                ? `${t.ms ?? 0} ms`
                : t.state === 'running'
                ? 'running…'
                : 'queued'}
            </span>
          </div>
        ))}
      </div>
      <p className="cua-lead">
        {partial}
        <span className="streaming-caret" />
      </p>
    </>
  )
}
