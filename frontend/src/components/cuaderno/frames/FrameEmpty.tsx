import type { EntryCue } from '../../../types/api'

type Props = { onAsk: (q: string) => void; entryCue?: EntryCue | null }

const mono = {
  fontFamily: 'var(--font-mono)',
  fontStyle: 'normal',
  fontSize: '0.85em',
} as const

// Rendering doctrine (prompts.py, get_entry_cue): "an AI burst shaped `X`
// ~N days ago; you haven't been back". If stale, scope the claim to "as of the
// last analysis ~N days ago" — never a present-tense gap past what analysis
// witnessed. A null cue means nothing to surface: the default copy, no invention.
export function FrameEmpty({ onAsk, entryCue }: Props) {
  const cue = entryCue ?? null
  return (
    <div className="empty">
      {cue ? (
        <>
          <h1 className="hi">
            An AI burst shaped{' '}
            <code style={mono}>{cue.file_path}</code>{' '}
            {cue.ai_burst_days === 0 ? 'today' : `~${cue.ai_burst_days} days ago`}.{' '}
            <em>
              {cue.never_human_touched
                ? 'No human commit has ever touched it.'
                : `You haven't been back in ${cue.last_contact_days} days.`}
            </em>
          </h1>
          <p className="sub">
            {cue.stale
              ? `As of the last analysis${
                  cue.analyzed_age_days != null ? ` ~${cue.analyzed_age_days} days ago` : ''
                } — the gap may have closed since. `
              : ''}
            Ask anything in your own words — every answer is anchored to real
            code; nothing invented.
          </p>
        </>
      ) : (
        <>
          <h1 className="hi">
            First time in this project. <em>What interests you?</em>
          </h1>
          <p className="sub">
            Ask anything in your own words — broad ("what does this project do?"),
            relational ("how do X and Y connect?"), or atomic ("why is line 152
            written this way?"). Every answer is anchored to real code; nothing
            invented.
          </p>
        </>
      )}
      <div className="starters">
        <div className="cap">{cue ? 'start from the gap' : 'or start from here'}</div>
        {cue && (
          <button
            className="starter"
            onClick={() =>
              onAsk(
                `why does ${cue.file_path} exist, and what shaped it in the last AI burst?`,
              )
            }
          >
            <span className="glyph">◆</span>
            <span>
              why does <code style={mono}>{cue.file_path}</code> exist, and what
              shaped it in the last AI burst?
            </span>
            <span className="arr">→</span>
          </button>
        )}
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
            <code style={mono}>
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
