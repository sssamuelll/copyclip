import { useState, useEffect, useSyncExternalStore } from 'react'
import type { PlaygroundWidgetData, Citation, CallDescriptor } from '../../../types/api'
import { CitationChip } from '../CitationChip'
import { subscribe, getState, launch, close, getToken } from '../playgroundSlot'
import { IdleInvitation } from '../stepper/IdleInvitation'
import { PreviewCall } from '../stepper/PreviewCall'
import { Spawning } from '../stepper/Spawning'
import { Stepper } from '../stepper/Stepper'
import { EndedCards } from '../stepper/EndedCards'
import { t } from '../strings'

type Props = {
  widget: PlaygroundWidgetData
  onOpenCitation: (c: Citation) => void
  lang?: string | null
}

// Build a faithful invocation string from the model's structured descriptor.
// Prefer the pre-rendered call_text; this is the fallback when only `call` is present.
// String args are repr-quoted (single quotes); other values use JSON.stringify.
//
// For method calls (call.ctor present): renders as `Ctor(ctorArgs).method(args)`.
// The constructor class name is derived from function_ref.qualname (e.g. "Foo.method"
// → "Foo"). When qualname is absent, falls back to rendering only the method call.
function callTextOf(name: string, call?: CallDescriptor): string {
  if (!call) return `${name}()`
  const lit = (v: unknown) => (typeof v === 'string' ? `'${v}'` : JSON.stringify(v))
  const pos = (call.args ?? []).map(lit)
  const kw = Object.entries(call.kwargs ?? {}).map(([k, v]) => `${k}=${lit(v)}`)
  const methodArgs = [...pos, ...kw].join(', ')
  if (call.ctor) {
    // Method call: build Ctor(ctorArgs).method(args)
    const ctorPos = (call.ctor.args ?? []).map(lit)
    const ctorKw = Object.entries(call.ctor.kwargs ?? {}).map(([k, v]) => `${k}=${lit(v)}`)
    const ctorArgs = [...ctorPos, ...ctorKw].join(', ')
    // Derive class name from qualname (e.g. "Foo.method" → "Foo")
    const qualname = call.function_ref.qualname
    const ctorName = qualname?.includes('.') ? qualname.split('.')[0] : null
    if (ctorName) {
      return `${ctorName}(${ctorArgs}).${name}(${methodArgs})`
    }
  }
  return `${name}(${methodArgs})`
}

export function PlaygroundWidget({ widget, onOpenCitation, lang }: Props) {
  const slot = useSyncExternalStore(subscribe, getState)
  const [previewing, setPreviewing] = useState(false)
  // Token captured when this widget entered previewing mode. If the global token
  // has advanced (another widget launched), the slot may have cycled spawning→empty
  // so fast that the useEffect below never saw the non-empty state. The token
  // comparison catches this race: if token changed since we entered preview mode,
  // this widget's preview is stale even when slot.kind==='empty'.
  const [previewToken, setPreviewToken] = useState<number>(-1)

  const fn = widget.function_ref
  const myKey = `${fn.file}:${fn.name}:${fn.line ?? ''}`
  const isMine = slot.kind !== 'empty' && 'widgetKey' in slot && slot.widgetKey === myKey
  const fileLine = fn.line != null ? `${fn.file}:${fn.line}` : fn.file
  // The REAL model-proposed invocation (D2): the pre-rendered text if the floor
  // emitted it, else built from the structured descriptor. Never a fake "name(…)".
  const proposedCall = widget.call_text ?? callTextOf(fn.name, widget.call)

  // When Widget B takes the slot (isMine becomes false and slot is non-empty),
  // reset our previewing flag so the stale preview cannot resurface later when
  // Widget B finishes and the slot returns to 'empty' (slot.kind==='empty' would
  // re-satisfy the `previewing && (slot.kind==='empty' || isMine)` guard).
  useEffect(() => {
    if (previewing && !isMine && slot.kind !== 'empty') {
      setPreviewing(false)
    }
  }, [previewing, isMine, slot.kind])

  // Token-based ownership guard: if the global token advanced past the value
  // captured at preview-entry, another widget launched — clear our stale preview
  // even if the slot has already returned to 'empty' (spawning→empty race).
  const currentToken = getToken()
  const previewIsStale = previewing && previewToken >= 0 && currentToken !== previewToken && !isMine

  // On confirm the (possibly edited) free text flows through as call_text (D2);
  // the structured descriptor rides along for the backend's repr-literal guard.
  const doLaunch = (callText: string) => {
    setPreviewing(false)
    setPreviewToken(-1)
    void launch(myKey, {
      source: 'cuaderno',
      function_ref: fn,
      suggested_inputs: widget.suggested_inputs,
      breadcrumb: widget.breadcrumb,
      call: widget.call,
      call_text: callText,
    })
  }

  // trace: the React stepper (guarded: empty trace should never reach here since
  // the slot converts trace.length===0 to nothing_ran, but belt-and-suspenders)
  if (isMine && slot.kind === 'trace') {
    return <Stepper response={slot.response} onClose={close} lang={lang} />
  }

  // nothing_ran: the call didn't enter the target function — show a dismissible note
  if (isMine && slot.kind === 'nothing_ran') {
    return (
      <div className="widget stepper-widget">
        <div className="playground-nothing-ran">
          <span>{slot.message}</span>
          <button onClick={close} aria-label="×">×</button>
        </div>
      </div>
    )
  }

  // live: fallback Marimo iframe box (unchanged path) + surviving context band
  if (isMine && slot.kind === 'live') {
    return (
      <div className="widget">
        <div className="widget-head">
          <span>
            <span className="kind">playground</span> ·{' '}
            <span className="widget-head-name">{fn.name}</span>
          </span>
          <button className="playground-close" onClick={close} title="close">×</button>
        </div>
        {widget.breadcrumb || widget.citation ? (
          <div className="playground-live-context">
            {widget.breadcrumb ? (<span className="playground-breadcrumb">{widget.breadcrumb}</span>) : null}
            {widget.citation ? (<CitationChip citation={widget.citation} onClick={onOpenCitation} />) : null}
          </div>
        ) : null}
        {slot.fallbackReason ? (
          <div className="playground-fallback-note">{t('playground_fallback_note', lang, { reason: slot.fallbackReason })}</div>
        ) : null}
        <div className="playground-live">
          <iframe
            src={slot.iframeUrl}
            sandbox="allow-scripts allow-same-origin allow-forms"
            title={fn.name}
          />
        </div>
      </div>
    )
  }

  // preview-call: shown before any real code runs (or after retry) — user can edit
  // Check this BEFORE ended so that onRetry → setPreviewing(true) wins over the
  // stale 'ended' slot state (the slot won't clear until the next launch resolves).
  // Slot-ownership guard: if the slot was taken by a DIFFERENT widget while this
  // widget's `previewing` flag was still true (e.g. Widget B fired its own
  // step-through), clear the stale preview so this widget cannot call doLaunch
  // and evict Widget B's active playground.
  // Token guard: also covers the spawning→empty race where the effect never fires.
  if (previewing && !previewIsStale && (slot.kind === 'empty' || isMine)) {
    return (
      <PreviewCall
        funcName={fn.name}
        initialCall={proposedCall}
        onConfirm={doLaunch}
        onCancel={() => { setPreviewing(false); setPreviewToken(-1) }}
        lang={lang}
      />
    )
  }

  // spawning: capture in progress
  if (isMine && slot.kind === 'spawning') {
    return (
      <Spawning
        funcName={fn.name}
        callText={proposedCall}
        citation={widget.citation}
        breadcrumb={widget.breadcrumb}
        onOpenCitation={onOpenCitation}
        lang={lang}
      />
    )
  }

  // ended/evicted/error: single relaunchable card — retry goes back to preview
  if (isMine && slot.kind === 'ended') {
    return (
      <EndedCards
        funcName={fn.name}
        reason={slot.reason}
        message={slot.message}
        onRetry={() => { setPreviewing(true); setPreviewToken(getToken()) }}
        onClose={close}
        citation={widget.citation}
        breadcrumb={widget.breadcrumb}
        onOpenCitation={onOpenCitation}
        lang={lang}
      />
    )
  }

  // idle invitation (default) — only pass onClose when slot is empty so × cannot
  // kill a foreign playground belonging to a different function.
  const handleClose = slot.kind === 'empty' ? close : undefined
  return (
    <IdleInvitation
      funcName={fn.name}
      fileLine={fileLine}
      onStepThrough={() => { setPreviewing(true); setPreviewToken(getToken()) }}
      onClose={handleClose}
      citation={widget.citation}
      breadcrumb={widget.breadcrumb}
      onOpenCitation={onOpenCitation}
      lang={lang}
    />
  )
}
