type Props = {
  value: 'got' | 'didnt' | null
  onSet: (v: 'got' | 'didnt') => void
}

export function GotItMarkers({ value, onSet }: Props) {
  if (value === null) {
    return (
      <div className="gotit">
        <span className="ask">does this answer the question?</span>
        <button className="gotit-btn" onClick={() => onSet('got')}>
          <span style={{ color: 'var(--accent-2)' }}>✓</span> I got this
        </button>
        <button className="gotit-btn" onClick={() => onSet('didnt')}>
          <span style={{ color: 'var(--accent)' }}>↻</span> I didn't
        </button>
      </div>
    )
  }
  if (value === 'got') {
    return (
      <div className="gotit">
        <button className="gotit-btn is-got">✓ marked: got this</button>
        <span className="gotit-msg">
          saved to <span style={{ color: 'var(--ink)' }}>this matters</span>. ask anything else when ready.
        </span>
      </div>
    )
  }
  return (
    <div className="gotit">
      <button className="gotit-btn is-didnt">↻ marked: didn't</button>
      <span className="gotit-msg">
        where did it break? try a follow-up below or rephrase.
      </span>
    </div>
  )
}
