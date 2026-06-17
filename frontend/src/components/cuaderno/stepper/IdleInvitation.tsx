import { t } from '../strings'
import { s } from './StateRow'

type Props = { funcName: string; fileLine: string; onStepThrough: () => void; onClose: () => void; lang?: string | null }

export function IdleInvitation({ funcName, fileLine, onStepThrough, onClose, lang }: Props) {
  return (
    <div className="widget stepper-widget">
      <div style={s('display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--hairline-soft);')}>
        <span style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>Playground</span>
        <span style={s('color:var(--ink-4);')}>·</span>
        <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--accent-ink);')}>{funcName}</span>
        <span style={s('flex:1;')} />
        <button onClick={onClose} aria-label="×" style={s('border:none;background:none;color:var(--ink-4);cursor:pointer;font-size:16px;line-height:1;')}>×</button>
      </div>
      <div style={{ ...s('display:flex;flex-direction:column;'), height: 430 }}>
        <div style={s('flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:24px;')}>
          <div style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-4);font-weight:600;margin-bottom:14px;')}>{t('playground_anchored', lang)}</div>
          <div style={s('font-family:var(--font-mono);font-size:19px;color:var(--ink);margin-bottom:6px;')}>{funcName}</div>
          <div style={s('font-family:var(--font-mono);font-size:11px;color:var(--ink-4);margin-bottom:26px;')}>{fileLine}</div>
          <button onClick={onStepThrough} className="stepper-primary" style={s('border:1px solid var(--accent-line);background:var(--accent-soft);color:var(--accent-ink);border-radius:9px;padding:10px 22px;font-size:14px;font-family:var(--font-ui);font-weight:500;cursor:pointer;display:inline-flex;align-items:center;gap:9px;')}>{t('playground_step_through', lang)} <span style={s('font-size:12px;')}>→</span></button>
          <div style={s('font-size:12px;color:var(--ink-3);margin-top:16px;')}>{t('playground_run_note', lang)}</div>
        </div>
        <div style={s('display:flex;align-items:center;gap:8px;padding:0 16px 13px;')}>
          <span style={s('width:5px;height:5px;border-radius:50%;background:var(--accent);opacity:.55;flex:none;')} />
          <span style={s('font-size:11.5px;color:var(--ink-3);')}>{t('playground_python_limit', lang)}</span>
        </div>
      </div>
    </div>
  )
}
