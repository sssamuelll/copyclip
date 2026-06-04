import { useSyncExternalStore } from 'react'
import type { PlaygroundWidgetData, Citation } from '../../../types/api'
import { CitationChip } from '../CitationChip'
import { t } from '../strings'
import { subscribe, getState, launch, close } from '../playgroundSlot'

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
    })
  }

  // live: iframe view
  if (isMine && slot.kind === 'live') {
    return (
      <div className="widget">
        <div className="widget-head">
          <span className="widget-head-name">{widget.function_ref.name}</span>
          <button
            className="playground-close"
            onClick={close}
            title="close"
          >
            ×
          </button>
        </div>
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
        <span className="widget-head-name">{widget.function_ref.name}</span>
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
