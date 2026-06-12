import { t } from './strings'

// Feedback on the ANSWER (the witnessed artifact), never a verdict on the human's
// mind. "does this answer the question?" -> 'answers' | 'not_yet'. The old
// 'I got this' / 'got'|'didnt' spoke comprehension the system cannot witness
// (Axiom-0); this is a sibling of the bookmark, not the refused W4-3 score.
type Props = {
  value: 'answers' | 'not_yet' | null
  onSet: (v: 'answers' | 'not_yet') => void
  language?: string | null
}

export function AnswerCheck({ value, onSet, language }: Props) {
  if (value === null) {
    return (
      <div className="gotit">
        <span className="ask">{t('answercheck_prompt', language)}</span>
        <button className="gotit-btn" onClick={() => onSet('answers')}>
          <span style={{ color: 'var(--accent-2)' }}>✓</span> {t('answercheck_yes', language)}
        </button>
        <button className="gotit-btn" onClick={() => onSet('not_yet')}>
          <span style={{ color: 'var(--accent)' }}>↻</span> {t('answercheck_no', language)}
        </button>
      </div>
    )
  }
  if (value === 'answers') {
    return (
      <div className="gotit">
        <button className="gotit-btn is-got">{t('answercheck_marked_yes', language)}</button>
        <span className="gotit-msg">
          {t('answercheck_saved_pre', language)}
          <span style={{ color: 'var(--ink)' }}>{t('answercheck_saved_mid', language)}</span>
          {t('answercheck_saved_post', language)}
        </span>
      </div>
    )
  }
  return (
    <div className="gotit">
      <button className="gotit-btn is-didnt">{t('answercheck_marked_no', language)}</button>
      <span className="gotit-msg">{t('answercheck_no_msg', language)}</span>
    </div>
  )
}
