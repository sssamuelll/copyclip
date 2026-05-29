import { useState } from 'react'
import type { Block, Citation, CuadernoQuestion, ToolRow } from '../../types/api'
import { Composer } from './Composer'
import { GotItMarkers } from './GotItMarkers'
import { SidePanel } from './SidePanel'
import { HistoryOverlay } from './HistoryOverlay'
import { FrameEmpty } from './frames/FrameEmpty'
import { FrameMidStream } from './frames/FrameMidStream'
import { FrameDynamic } from './frames/FrameDynamic'

type Props = {
  sessionLabel: string
  questionNumber: string
  questions: CuadernoQuestion[]
  activeQuestion: CuadernoQuestion | null
  isLoading: boolean
  streamingQuestion?: string
  partialBlocks?: Block[]
  toolCalls?: ToolRow[]
  onAsk: (question: string) => void
  onSelectFromHistory: (position: number) => void
  onSetGotIt: (position: number, value: 'got' | 'didnt') => void
}

export function Cuaderno({
  sessionLabel,
  questionNumber,
  questions,
  activeQuestion,
  isLoading,
  streamingQuestion = '',
  partialBlocks = [],
  toolCalls = [],
  onAsk,
  onSelectFromHistory,
  onSetGotIt,
}: Props) {
  const [sidePanelFor, setSidePanelFor] = useState<Citation | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)

  const scene: 'empty' | 'midstream' | 'writing' | 'frame' = !isLoading
    ? activeQuestion
      ? 'frame'
      : 'empty'
    : partialBlocks.length > 0
    ? 'writing'
    : 'midstream'

  return (
    <div className="cuaderno theme-light accent-sienna density-regular">
      <div className="cua-top">
        <div className="crumb">
          <span className="dot" />
          <span className="here">copyclip</span>
          <span className="sep">·</span>
          <span>cuaderno</span>
          <span className="sep">·</span>
          <span style={{ color: 'var(--ink-2)' }}>{sessionLabel}</span>
        </div>
        <div className="right">
          <span className="session">{questionNumber}</span>
          <button
            className="hamb"
            onClick={() => setHistoryOpen((h) => !h)}
            aria-label="session history"
          >
            ≡
          </button>
        </div>
      </div>

      <div className="cua-stage swap-fade">
        <div className="cua-frame-wrap">
          <div className="cua-frame" key={activeQuestion?.position ?? scene}>
            {scene === 'empty' && <FrameEmpty onAsk={onAsk} />}
            {scene === 'midstream' && (
              <FrameMidStream
                question={streamingQuestion || questions[questions.length - 1]?.question || '…'}
                tools={toolCalls}
                partial=""
              />
            )}
            {scene === 'writing' && (
              <FrameDynamic
                frame={{ question: streamingQuestion, blocks: partialBlocks }}
                onOpenCitation={setSidePanelFor}
                onAsk={onAsk}
              />
            )}
            {scene === 'frame' && activeQuestion && (
              <>
                <FrameDynamic
                  frame={activeQuestion.frame}
                  onOpenCitation={setSidePanelFor}
                  onAsk={onAsk}
                />
                <GotItMarkers
                  value={activeQuestion.got_it}
                  onSet={(v) => onSetGotIt(activeQuestion.position, v)}
                />
              </>
            )}
          </div>
        </div>

        <Composer onSubmit={onAsk} disabled={isLoading} />

        {sidePanelFor && (
          <SidePanel citation={sidePanelFor} onClose={() => setSidePanelFor(null)} />
        )}

        {historyOpen && (
          <HistoryOverlay
            questions={questions}
            activePosition={activeQuestion?.position ?? null}
            onSelect={(p) => {
              setHistoryOpen(false)
              onSelectFromHistory(p)
            }}
            onClose={() => setHistoryOpen(false)}
          />
        )}
      </div>
    </div>
  )
}
