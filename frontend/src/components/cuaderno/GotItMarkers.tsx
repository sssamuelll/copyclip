import { t } from './strings'

type Props = {
  value: 'got' | 'didnt' | null
  onSet: (v: 'got' | 'didnt') => void
  language?: string | null
}

export function GotItMarkers({ value, onSet, language }: Props) {
  if (value === null) {
    return (
      <div className="gotit">
        <span className="ask">{t('gotit_prompt', language)}</span>
        <button className="gotit-btn" onClick={() => onSet('got')}>
          <span style={{ color: 'var(--accent-2)' }}>✓</span> {t('gotit_got', language)}
        </button>
        <button className="gotit-btn" onClick={() => onSet('didnt')}>
          <span style={{ color: 'var(--accent)' }}>↻</span> {t('gotit_didnt', language)}
        </button>
      </div>
    )
  }
  if (value === 'got') {
    return (
      <div className="gotit">
        <button className="gotit-btn is-got">{t('gotit_marked_got', language)}</button>
        <span className="gotit-msg">
          {t('gotit_saved_pre', language)}
          <span style={{ color: 'var(--ink)' }}>{t('gotit_saved_mid', language)}</span>
          {t('gotit_saved_post', language)}
        </span>
      </div>
    )
  }
  return (
    <div className="gotit">
      <button className="gotit-btn is-didnt">{t('gotit_marked_didnt', language)}</button>
      <span className="gotit-msg">{t('gotit_didnt_msg', language)}</span>
    </div>
  )
}
