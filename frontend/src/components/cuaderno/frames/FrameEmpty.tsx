import type { EntryCue } from '../../../types/api'

type Props = { onAsk: (q: string) => void; entryCue?: EntryCue | null }

const mono = {
  fontFamily: 'var(--font-mono)',
  fontStyle: 'normal',
  fontSize: '0.85em',
} as const

const nDays = (n: number) => (n === 1 ? '1 day' : `${n} days`)

// The gap claim, rescoped per the doctrine (prompts.py, get_entry_cue): the
// burst itself is a witnessed commit — its age is exact even over a stale
// table — but the ABSENCE of a return is only witnessed up to the last
// analysis. So when stale=true the gap claim itself carries the scope and
// drops to past tense; it is never asserted as a present-tense fact.
function gapClaim(cue: EntryCue): string {
  const scope = cue.stale
    ? `As of the last analysis ~${nDays(cue.analyzed_age_days ?? 0)} ago, `
    : ''
  if (cue.never_human_touched) {
    return cue.stale
      ? `${scope}no human commit had touched it.`
      : 'No human commit has ever touched it.'
  }
  if (cue.last_contact_days === 0) {
    return cue.stale
      ? `${scope}you hadn't been back after your same-day touch.`
      : 'You touched it earlier today — the burst came after.'
  }
  return cue.stale
    ? `${scope}you hadn't been back in ${nDays(cue.last_contact_days)}.`
    : `You haven't been back in ${nDays(cue.last_contact_days)}.`
}

// A null cue means nothing honest to surface: neutral copy, no invention —
// including no "first time" claim the system cannot witness either.
export function FrameEmpty({ onAsk, entryCue }: Props) {
  const cue = entryCue ?? null
  return (
    <div className="empty">
      {cue ? (
        <>
          <h1 className="hi">
            An AI burst shaped{' '}
            <code style={mono}>{cue.file_path}</code>{' '}
            {cue.ai_burst_days === 0 ? 'today' : `~${nDays(cue.ai_burst_days)} ago`}.{' '}
            <em>{gapClaim(cue)}</em>
          </h1>
          <p className="sub">
            {cue.stale ? 'That may have changed since. ' : ''}
            Ask anything in your own words — every answer is anchored to real
            code; nothing invented.
          </p>
        </>
      ) : (
        <>
          <h1 className="hi">
            <em>What interests you?</em>
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
