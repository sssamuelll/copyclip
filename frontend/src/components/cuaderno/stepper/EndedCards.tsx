import { t } from '../strings'
import { s } from './StateRow'

type Reason = 'closed' | 'evicted' | 'exited' | 'error'
type Props = { funcName: string; reason: Reason; message?: string; onRetry: () => void; onClose: () => void; lang?: string | null }

export function EndedCards({ funcName, reason, message, onRetry, onClose, lang }: Props) {
  const spec = reason === 'evicted'
    ? { tick: 'var(--ink-4)', tickOpacity: '', title: t('playground_evicted_title', lang), body: t('playground_evicted_body', lang), btn: t('playground_bring_back', lang) }
    : reason === 'error'
      ? { tick: 'var(--neg-ink)', tickOpacity: '.7', title: t('playground_spawn_error', lang), body: message ?? t('playground_spawn_error_body', lang), btn: t('playground_try_again', lang) }
      : { tick: 'var(--ink-4)', tickOpacity: '', title: t('playground_runtime_closed', lang), body: t('playground_runtime_closed_body', lang), btn: t('playground_reopen', lang) }
  return (
    <div className="widget stepper-widget">
      <div style={s('display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--hairline-soft);')}>
        <span style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>Playground</span>
        <span style={s('color:var(--ink-4);')}>·</span>
        <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--accent-ink);')}>{funcName}</span>
        <span style={s('flex:1;')} />
        <button onClick={onClose} aria-label="×" style={s('border:none;background:none;color:var(--ink-4);cursor:pointer;font-size:16px;line-height:1;')}>×</button>
      </div>
      <div style={s('padding:18px;display:flex;flex-direction:column;gap:12px;')}>
        <div style={s('display:flex;align-items:center;gap:9px;')}>
          <span style={s(`width:8px;height:8px;border-radius:2px;background:${spec.tick};${spec.tickOpacity ? `opacity:${spec.tickOpacity};` : ''}`)} />
          <span style={s('font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>{spec.title}</span>
        </div>
        <div style={s('font-size:13px;line-height:1.5;color:var(--ink-2);')}>{spec.body}</div>
        <button onClick={onRetry} className="stepper-ghost" style={s('align-self:flex-start;border:1px solid var(--hairline);background:var(--paper);color:var(--accent-ink);border-radius:7px;padding:7px 14px;font-size:12.5px;font-family:var(--font-ui);cursor:pointer;')}>{spec.btn}</button>
      </div>
    </div>
  )
}
