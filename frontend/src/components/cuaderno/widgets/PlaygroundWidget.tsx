import { useSyncExternalStore } from 'react'
import type { PlaygroundWidgetData, Citation } from '../../../types/api'
import { CitationChip } from '../CitationChip'
import { subscribe, getState, launch, close } from '../playgroundSlot'
import { Stepper } from '../stepper/Stepper'
import { IdleInvitation } from '../stepper/IdleInvitation'
import { Spawning } from '../stepper/Spawning'
import { EndedCards } from '../stepper/EndedCards'

type Props = {
  widget: PlaygroundWidgetData
  onOpenCitation: (c: Citation) => void
  lang?: string | null
}

export function PlaygroundWidget({ widget, onOpenCitation, lang }: Props) {
  const slot = useSyncExternalStore(subscribe, getState)

  const myKey = `${widget.function_ref.file}:${widget.function_ref.name}:${widget.function_ref.line ?? ''}`
  const isMine = slot.kind !== 'empty' && slot.widgetKey === myKey

  const handleLaunch = () => {
    void launch(myKey, {
      source: 'cuaderno',
      function_ref: widget.function_ref,
      suggested_inputs: widget.suggested_inputs,
      breadcrumb: widget.breadcrumb,
      // Forward the model's proposed call descriptor (args/kwargs/ctor) so the
      // backend can build a real CallDescriptor and run the step-through trace.
      // Without this field the launch always arrives with req.call = None and
      // any method target immediately falls back to the Marimo iframe.
      ...(widget.call !== undefined ? { call: widget.call } : {}),
    })
  }

  // trace: step-through capture — delegate entirely to <Stepper>.
  // No subprocess to manage; close() transitions the slot to ended.
  if (isMine && slot.kind === 'trace') {
    return <Stepper response={slot.response} onClose={close} lang={lang} />
  }

  // live: iframe view — the editorial frame survives the click (header band +
  // breadcrumb + citation stay), so the running thing reads as one composed
  // widget, not a foreign window that replaced the page.
  if (isMine && slot.kind === 'live') {
    return (
      <div className="widget">
        <div className="widget-head">
          <span>
            <span className="kind">playground</span> ·{' '}
            <span className="widget-head-name">{widget.function_ref.name}</span>
          </span>
          <button className="playground-close" onClick={close} title="close">
            ×
          </button>
        </div>
        {widget.breadcrumb || widget.citation ? (
          <div className="playground-live-context">
            {widget.breadcrumb ? (
              <span className="playground-breadcrumb">{widget.breadcrumb}</span>
            ) : null}
            {widget.citation ? (
              <CitationChip citation={widget.citation} onClick={onOpenCitation} />
            ) : null}
          </div>
        ) : null}
        <div className="playground-live">
          <iframe
            src={slot.iframeUrl}
            sandbox="allow-scripts allow-same-origin allow-forms"
            title={widget.function_ref.name}
          />
        </div>
      </div>
    )
  }

  // ended: delegate to EndedCards for 3-way reason dispatch with correct
  // tokens, body copy, and retry/close callbacks.
  if (isMine && slot.kind === 'ended') {
    return (
      <EndedCards
        funcName={widget.function_ref.name}
        reason={slot.reason}
        message={slot.message}
        onRetry={handleLaunch}
        onClose={close}
        citation={widget.citation}
        breadcrumb={widget.breadcrumb}
        onOpenCitation={onOpenCitation}
        lang={lang}
      />
    )
  }

  // spawning: delegate to Spawning for animated progress state.
  if (isMine && slot.kind === 'spawning') {
    const callText = widget.call_text ?? widget.breadcrumb ?? widget.function_ref.name
    return (
      <Spawning
        funcName={widget.function_ref.name}
        callText={callText}
        citation={widget.citation}
        breadcrumb={widget.breadcrumb}
        onOpenCitation={onOpenCitation}
        lang={lang}
      />
    )
  }

  // idle: not mine (slot is empty or belongs to another widget).
  // Delegate to IdleInvitation so the user can step through from here.
  // Only pass onClose when the slot is empty — if another widget currently
  // owns the slot (kind='spawning'/'live'/'trace') the × button would call
  // close() and kill the active playground belonging to a different function.
  const fileLine = widget.function_ref.line != null
    ? `${widget.function_ref.file}:${widget.function_ref.line}`
    : widget.function_ref.file
  const handleClose = slot.kind === 'empty' ? close : undefined
  return (
    <IdleInvitation
      funcName={widget.function_ref.name}
      fileLine={fileLine}
      onStepThrough={handleLaunch}
      onClose={handleClose}
      citation={widget.citation}
      breadcrumb={widget.breadcrumb}
      onOpenCitation={onOpenCitation}
      lang={lang}
    />
  )
}
