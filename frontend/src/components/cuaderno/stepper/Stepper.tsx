import { useState, useRef, useMemo } from 'react'
import type { StepThroughResponse } from '../../../types/api'
import { t } from '../strings'
import {
  ROW_H, clampStep, nextChange, trackFraction, lineModels, buildRows, markerLefts, sourceTranslateY,
} from './trace'
import { StateRow, s } from './StateRow'

type Props = {
  response: StepThroughResponse
  onClose: () => void
  lang?: string | null
}

export function Stepper({ response, onClose, lang }: Props) {
  const { trace, source_lines, func_name, file_line, truncated, truncated_reason } = response
  const total = trace.length
  const [step, setStep] = useState(1)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  // Belt-and-suspenders: empty trace should never reach Stepper (the slot converts
  // it to 'nothing_ran'), but guard here too so we never index trace[cur-1] on [].
  if (total === 0) {
    return (
      <div className="widget stepper-widget">
        <div style={{ padding: '16px', color: 'var(--ink-3)', fontFamily: 'var(--font-ui)', fontSize: '13px' }}>
          {func_name}: no steps captured — the call did not enter this function.
          <button onClick={onClose} aria-label="×" style={{ marginLeft: '12px', border: 'none', background: 'none', cursor: 'pointer', color: 'var(--ink-4)' }}>×</button>
        </div>
      </div>
    )
  }

  // Synchronous derived-state reset: compare the current response identity to the
  // previous one via a ref.  When they differ we reset step/expanded during this
  // render (before any JSX is evaluated), so there is never a frame where stale
  // expansion state is visible.  This replaces the old useEffect approach which
  // caused a 1-frame flash: old expanded map was live on the first render with the
  // new response, then cleared by the effect after paint.
  const prevResponseRef = useRef<StepThroughResponse>(response)
  if (prevResponseRef.current !== response) {
    prevResponseRef.current = response
    // Reset derived state synchronously — no extra render, no flash.
    // Calling setX during render is valid in React when guarded by a ref comparison.
    setStep(1)
    setExpanded({})
  }

  const cur = clampStep(step, total)
  const tr = trace[cur - 1]
  const curIdx = source_lines.findIndex((l) => l.num === tr.line)
  const staleAnchor = curIdx < 0   // spec §7: source moved, line not found
  const lines = lineModels(source_lines, curIdx)
  const rows = buildRows(tr, expanded)
  const hlTop = curIdx * ROW_H     // only used when !staleAnchor
  const handleLeft = total > 1 ? `${((cur - 1) / (total - 1)) * 100}%` : '0%'
  const markers = markerLefts(trace)

  // raised: only treated as terminal if it's also the last step (cur === total)
  const raised = (tr.event === 'raise' || !!tr.raised) && cur === total
  // raised wins over truncated: a terminal throw always shows the red band,
  // even if the trace was also cut short by the step cap or a time limit.
  const slabBg = raised ? 'var(--neg)' : 'var(--accent-soft)'
  const slabBorder = raised ? 'var(--neg-ink)' : 'var(--accent)'
  const truncatedText = truncated_reason === 'steps'
    ? t('playground_truncated_steps', lang, { n: String(total) })
    : truncated_reason === 'time'
      ? t('playground_truncated_time', lang, { n: String(total) })
      : t('playground_truncated', lang, { n: String(total) })
  const banner = raised
    ? { tick: 'var(--neg-ink)', bg: 'var(--neg)', ink: 'var(--neg-ink)', text: t('playground_raised_final', lang) }
    : truncated
      ? { tick: 'var(--accent)', bg: 'var(--surface-2)', ink: 'var(--ink-2)', text: truncatedText }
      : null
  // Heights are CSS custom properties on .stepper-widget so density themes can override them.
  // --stepper-h = 480px (normal), --stepper-h-banner = 404px (banner present).
  const bodyHeight = banner ? 'var(--stepper-h-banner)' : 'var(--stepper-h)'
  // terminal = the trace has reached a natural end: truncation cap or a raise at the last step.
  // In these states the handoff omits "next change ◆" and the honesty note (pixel-fidelity).
  const terminal = truncated || raised
  // Compute the translateY so the highlighted line stays visible inside the
  // clipped source column (overflow:hidden). The visible height estimate uses
  // the numeric defaults matching the CSS var defaults (480 or 404). If the
  // theme overrides --stepper-h, the highlight may be slightly off-center but
  // never invisible.
  const bodyHeightPx = banner ? 404 : 480
  const sourceVisibleH = bodyHeightPx - 29 - 52 - (terminal ? 0 : 25)
  const srcTranslateY = sourceTranslateY(curIdx, source_lines.length, sourceVisibleH)

  const toggle = (name: string) =>
    setExpanded((e) => ({ ...e, [name]: !e[name] }))
  const move = (d: number) => setStep(clampStep(cur + d, total))
  const onTrack = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const f = (e.clientX - r.left) / r.width
    setStep(trackFraction(f, total))
  }
  const onNextChange = () => setStep(nextChange(cur, trace))
  const atEnd = cur >= total

  // Raised terminal handle: use --neg-ink instead of --accent (handoff state 07, line 521).
  // raised wins over truncated: if the last step threw, the handle is red regardless.
  const handleColor = raised ? 'var(--neg-ink)' : 'var(--accent)'

  const btn = 'width:28px;height:28px;flex:none;border-radius:7px;border:1px solid var(--hairline);background:var(--stepper-btn-bg);color:var(--ink-2);cursor:pointer;font-size:9px;display:flex;align-items:center;justify-content:center;'

  return (
    <div className="widget stepper-widget">
      {/* head strip */}
      <div style={s('display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--hairline-soft);')}>
        <span style={s('font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>Playground</span>
        <span style={s('color:var(--ink-4);')}>·</span>
        <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--accent-ink);')}>{func_name}</span>
        <span style={s('flex:1;')} />
        <span style={s('font-family:var(--font-mono);font-size:12px;color:var(--ink-3);font-variant-numeric:tabular-nums;')}>step {cur} / {total}</span>
        <button onClick={onClose} aria-label="×" style={s('border:none;background:none;color:var(--ink-4);cursor:pointer;font-size:16px;line-height:1;padding:0 2px;')}>×</button>
      </div>
      {/* breadcrumb */}
      <div style={s('padding:11px 16px 12px;border-bottom:1px solid var(--hairline-soft);')}>
        <div style={s('font-family:var(--font-body);font-size:15px;color:var(--ink);')}>
          {t('playground_step_through', lang)} <span style={s('font-family:var(--font-mono);font-size:13px;color:var(--accent-ink);')}>{func_name}</span>
        </div>
        <div style={s('font-family:var(--font-mono);font-size:11px;color:var(--ink-4);margin-top:3px;')}>{file_line}</div>
      </div>
      {/* banner */}
      {banner && (
        <div style={s(`display:flex;align-items:center;gap:9px;padding:9px 16px;background:${banner.bg};border-bottom:1px solid var(--hairline-soft);`)}>
          <span style={s(`display:inline-block;width:3px;height:13px;border-radius:1px;background:${banner.tick};flex:none;`)} />
          <span style={s(`font-size:12px;color:${banner.ink};font-family:var(--font-ui);`)}>{banner.text}</span>
        </div>
      )}
      {/* body */}
      <div style={{ ...s('display:flex;flex-direction:column;padding:16px 16px 13px;'), height: bodyHeight }}>
        <div style={s('flex:1;display:flex;min-height:0;')}>
          {/* source */}
          <div style={s('flex:1.55;position:relative;overflow:hidden;font-family:var(--font-mono);font-size:13px;line-height:26px;')}>
            {!staleAnchor && (
              <div data-testid="hl-slab" style={{ ...s(`position:absolute;left:-16px;right:6px;height:26px;background:${slabBg};border-left:2px solid ${slabBorder};transition:top .22s cubic-bezier(.4,0,.2,1);`), top: hlTop + srcTranslateY }} />
            )}
            <div
              data-testid="source-lines"
              style={{ ...s('position:relative;'), transform: `translateY(${srcTranslateY}px)`, transition: 'transform .22s cubic-bezier(.4,0,.2,1)' }}
            >
              {lines.map((ln) => (
                <div key={ln.num} style={s('display:flex;height:26px;')}>
                  <span style={s(ln.numStyle)}>{ln.num}</span>
                  <span style={s(ln.codeStyle)}>{ln.code}</span>
                </div>
              ))}
            </div>
          </div>
          {/* divider */}
          <div style={s('width:1px;background:var(--hairline-soft);margin:0 16px;flex:none;')} />
          {/* state */}
          <div style={s('flex:1;min-width:0;display:flex;flex-direction:column;')}>
            <div style={s('display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px;')}>
              <span style={s('font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);font-weight:600;')}>{t('playground_state', lang)}</span>
              <span style={s('font-family:var(--font-mono);font-size:11px;color:var(--ink-4);font-variant-numeric:tabular-nums;')}>step {cur}</span>
            </div>
            <div style={s('flex:1;overflow:auto;font-family:var(--font-mono);font-size:12.5px;')}>
              {rows.map((row, i) => (<StateRow key={`${row.name}-${i}`} row={row} onToggle={toggle} />))}
              {tr.raised && (
                <div style={s('margin-top:10px;padding:9px 11px;background:var(--neg);border:1px solid var(--neg-line);border-radius:8px;')}>
                  <div style={s('font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--neg-ink);font-family:var(--font-ui);font-weight:600;margin-bottom:4px;')}>{t('playground_raised_label', lang)}</div>
                  <div style={s('color:var(--neg-ink);font-weight:600;')}>{tr.raised.type}: {tr.raised.message}</div>
                </div>
              )}
            </div>
          </div>
        </div>
        {/* scrubber */}
        <div style={s('display:flex;align-items:center;gap:11px;padding-top:13px;margin-top:11px;border-top:1px solid var(--hairline-soft);')}>
          <button onClick={() => move(-1)} aria-label="Previous step" className="stepper-btn" style={s(btn)}>◀</button>
          <div
            role="slider"
            tabIndex={0}
            aria-valuemin={1}
            aria-valuemax={total}
            aria-valuenow={cur}
            onClick={onTrack}
            onKeyDown={(e) => {
              if (e.key === 'ArrowRight' || e.key === 'ArrowUp') { e.preventDefault(); move(1) }
              else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') { e.preventDefault(); move(-1) }
              else if (e.key === 'Home') { e.preventDefault(); setStep(1) }
              else if (e.key === 'End') { e.preventDefault(); setStep(total) }
            }}
            style={s('position:relative;flex:1;height:26px;display:flex;align-items:center;cursor:pointer;')}
          >
            <div style={s('position:absolute;left:0;right:0;height:3px;border-radius:2px;background:var(--hairline);')} />
            <div style={{ ...s('position:absolute;left:0;height:3px;border-radius:2px;background:var(--accent-line);transition:width .22s cubic-bezier(.4,0,.2,1);'), width: handleLeft }} />
            {markers.map((left, i) => (
              <div key={i} style={{ ...s('position:absolute;top:50%;transform:translate(-50%,-50%);width:2px;height:11px;border-radius:1px;background:var(--accent-line);'), left: `${left}%` }} />
            ))}
            <div style={{ ...s(`position:absolute;width:13px;height:13px;border-radius:50%;background:${handleColor};border:2px solid var(--surface);transform:translateX(-50%);transition:left .22s cubic-bezier(.4,0,.2,1);box-shadow:0 1px 3px rgba(0,0,0,.3);`), left: handleLeft }} />
          </div>
          <button onClick={() => move(1)} aria-label="Next step" className="stepper-btn" style={{ ...s(btn), ...(atEnd ? s('color:var(--ink-4);') : {}) }}>▶</button>
          {!terminal && (
            <button onClick={onNextChange} className="stepper-btn" style={s('flex:none;height:28px;border-radius:7px;border:1px solid var(--hairline);background:var(--stepper-btn-bg);color:var(--ink-3);cursor:pointer;font-size:11px;padding:0 11px;white-space:nowrap;')}>{t('playground_next_change', lang)}</button>
          )}
        </div>
        {/* honesty note — hidden in terminal states (truncated/raised) to match handoff */}
        {!terminal && (
          <div style={s('display:flex;align-items:center;gap:8px;margin-top:11px;')}>
            <span style={s('width:5px;height:5px;border-radius:50%;background:var(--accent);opacity:.55;flex:none;')} />
            <span style={s('font-size:11.5px;color:var(--ink-3);')}>{t('playground_python_limit', lang)}</span>
          </div>
        )}
      </div>
    </div>
  )
}
