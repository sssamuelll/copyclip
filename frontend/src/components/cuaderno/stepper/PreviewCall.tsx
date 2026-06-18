import { useState } from 'react'
import { t } from '../strings'
import { s } from './StateRow'

type Props = {
  funcName: string
  initialCall: string             // the REAL model-proposed invocation (from widget.call_text)
  onConfirm: (callText: string, dirty: boolean) => void
  onCancel: () => void
  needsArgs?: boolean             // floor widget: open directly into editing with a completion hint
  lang?: string | null
}

export function PreviewCall({ funcName, initialCall, onConfirm, onCancel, needsArgs, lang }: Props) {
  // needs_args widgets open directly into edit mode so the user can complete the call
  const [editing, setEditing] = useState(needsArgs === true)
  const [callText, setCallText] = useState(initialCall)
  const [dirty, setDirty] = useState(false)
  return (
    <div className="widget stepper-widget">
      <div style={s('display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--hairline-soft);')}>
        <span style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>Playground</span>
        <span style={s('color:var(--ink-4);')}>·</span>
        <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--accent-ink);')}>{funcName}</span>
        <span style={s('flex:1;')} />
        <button onClick={onCancel} aria-label="×" style={s('border:none;background:none;color:var(--ink-4);cursor:pointer;font-size:16px;line-height:1;')}>×</button>
      </div>
      <div style={{ ...s('display:flex;flex-direction:column;padding:18px 16px 13px;'), height: 'var(--stepper-preview-h)' }}>
        <div style={s('flex:1;display:flex;flex-direction:column;justify-content:center;')}>
          <div style={s('font-family:var(--font-body);font-size:15px;color:var(--ink-2);margin-bottom:13px;')}>{t('playground_preview_lead', lang)}</div>
          {needsArgs ? (
            <div
              data-testid="needs-args-hint"
              style={s('font-size:12.5px;color:var(--accent-ink);margin-bottom:10px;')}
            >
              {t('playground_complete_call', lang)}
            </div>
          ) : null}
          {editing ? (
            <textarea
              value={callText}
              onChange={(e) => { setCallText(e.target.value); setDirty(true) }}
              spellCheck={false}
              style={s('font-family:var(--font-mono);font-size:14px;color:var(--ink);background:var(--surface-2);border:1px solid var(--accent-line);border-radius:9px;padding:13px 14px;width:100%;resize:none;height:62px;line-height:1.5;outline:none;')}
            />
          ) : (
            <div style={s('position:relative;font-family:var(--font-mono);font-size:14px;color:var(--ink);background:var(--surface-2);border:1px solid var(--hairline);border-radius:9px;padding:13px 46px 13px 14px;line-height:1.5;')}>
              {callText}
              <button onClick={() => setEditing(true)} aria-label="✎" className="stepper-pencil" style={s('position:absolute;right:9px;top:9px;border:1px solid var(--hairline);background:var(--paper);color:var(--ink-3);border-radius:6px;width:28px;height:28px;cursor:pointer;font-size:12px;')}>✎</button>
            </div>
          )}
          <div style={s('display:flex;align-items:center;gap:8px;margin-top:13px;')}>
            <span style={s('width:5px;height:5px;border-radius:50%;background:var(--accent);opacity:.55;flex:none;')} />
            <span style={s('font-size:12.5px;color:var(--ink-3);')}>{t('playground_run_note', lang)}</span>
          </div>
        </div>
        <div style={s('display:flex;align-items:center;gap:10px;padding-top:13px;border-top:1px solid var(--hairline-soft);')}>
          <button onClick={() => onConfirm(callText, dirty)} className="stepper-primary" style={s('border:1px solid var(--accent-line);background:var(--accent-soft);color:var(--accent-ink);border-radius:8px;padding:9px 18px;font-size:13.5px;font-weight:500;font-family:var(--font-ui);cursor:pointer;')}>{t('playground_step_through', lang)}</button>
          {!needsArgs ? (
            <button onClick={() => setEditing((val) => !val)} style={s('border:1px solid var(--hairline);background:var(--paper);color:var(--ink-3);border-radius:8px;padding:9px 16px;font-size:13.5px;font-family:var(--font-ui);cursor:pointer;')}>{t('playground_edit_call', lang)}</button>
          ) : null}
          <span style={s('flex:1;')} />
          <button onClick={onCancel} style={s('border:none;background:none;color:var(--ink-4);font-size:13px;cursor:pointer;font-family:var(--font-ui);')}>{t('playground_cancel', lang)}</button>
        </div>
      </div>
    </div>
  )
}
