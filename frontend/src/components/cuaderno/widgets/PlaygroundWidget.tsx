import { useSyncExternalStore } from 'react'
import type { PlaygroundWidgetData, Citation } from '../../../types/api'
import { CitationChip } from '../CitationChip'
import { t } from '../strings'
import { subscribe, getState, launch, close } from '../playgroundSlot'
import { Stepper } from '../stepper/Stepper'

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

  // ended: idle layout + status note + re-launchable button
  let endedNote: string | null = null
  if (isMine && slot.kind === 'ended') {
    if (slot.reason === 'evicted') {
      endedNote = t('playground_evicted', lang)
    } else if (slot.reason === 'error') {
      endedNote = slot.message ?? t('playground_ended', lang)
    } else {
      endedNote = t('playground_ended', lang)
    }
  }

  // spawning: show preparing state
  const isSpawning = isMine && slot.kind === 'spawning'

  return (
    <div className="widget">
      <div className="widget-head">
        <span>
          <span className="kind">playground</span> ·{' '}
          <span className="widget-head-name">{widget.function_ref.name}</span>
        </span>
      </div>
      <div className="widget-body">
        {widget.citation ? (
          <CitationChip citation={widget.citation} block onClick={onOpenCitation} />
        ) : null}
        {widget.breadcrumb ? (
          <div className="playground-breadcrumb">{widget.breadcrumb}</div>
        ) : null}
        {endedNote ? (
          <div className="graph-view-note playground-status-note">{endedNote}</div>
        ) : null}
        {isSpawning ? (
          <div className="playground-preparing">{t('playground_preparing', lang)}</div>
        ) : (
          <button className="btn-accent playground-run" onClick={handleLaunch}>
            {t('playground_run', lang)}
          </button>
        )}
      </div>
    </div>
  )
}
