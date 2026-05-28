type Props = { onAsk: (q: string) => void }

export function FrameEmpty({ onAsk }: Props) {
  return (
    <div className="empty">
      <h1 className="hi">
        First time in this project. <em>What interests you?</em>
      </h1>
      <p className="sub">
        Ask anything in your own words — broad ("what does this project do?"),
        relational ("how do X and Y connect?"), or atomic ("why is line 152
        written this way?"). Every answer is anchored to real code; nothing
        invented.
      </p>
      <div className="starters">
        <div className="cap">or start from here</div>
        <button
          className="starter"
          onClick={() => onAsk('what does this project do?')}
        >
          <span className="glyph">A</span>
          <span>what does this project do?</span>
          <span className="arr">→</span>
        </button>
        <button
          className="starter"
          onClick={() =>
            onAsk('how do the analyzer and the playground connect?')
          }
        >
          <span className="glyph">B</span>
          <span>how do the analyzer and the playground connect?</span>
          <span className="arr">→</span>
        </button>
        <button
          className="starter"
          onClick={() =>
            onAsk(
              'why does _module_from_relpath use slash instead of dot?',
            )
          }
        >
          <span className="glyph">C</span>
          <span>
            why does{' '}
            <code style={{ fontFamily: 'var(--font-mono)', fontStyle: 'normal', fontSize: '0.85em' }}>
              _module_from_relpath
            </code>{' '}
            use slash instead of dot?
          </span>
          <span className="arr">→</span>
        </button>
      </div>
    </div>
  )
}
