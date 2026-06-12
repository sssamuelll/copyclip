import { useState } from 'react'
import type { Block, Citation, CuadernoQuestion, ToolRow, CuadernoProvidersResponse } from '../../types/api'
import { SURVIVOR_NAV, type SurvivorPage } from '../../nav'
import { Composer } from './Composer'
import { AnswerCheck } from './AnswerCheck'
import { SidePanel } from './SidePanel'
import { HistoryOverlay } from './HistoryOverlay'
import { FrameEmpty } from './frames/FrameEmpty'
import { FrameMidStream } from './frames/FrameMidStream'
import { FrameDynamic } from './frames/FrameDynamic'
import { ProviderSelector } from './ProviderSelector'

type Props = {
  sessionLabel: string
  questionNumber: string
  questions: CuadernoQuestion[]
  activeQuestion: CuadernoQuestion | null
  isLoading: boolean
  streamingQuestion?: string
  partialBlocks?: Block[]
  toolCalls?: ToolRow[]
  providers?: CuadernoProvidersResponse | null
  onSetProvider?: (provider: string, model: string) => void
  onNavigate?: (target: SurvivorPage) => void
  onAsk: (question: string) => void
  onSelectFromHistory: (position: number) => void
  onSetAnswerCheck: (position: number, value: 'answers' | 'not_yet') => void
  questionLanguage?: string | null
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
  providers = null,
  onSetProvider,
  onNavigate,
  onAsk,
  onSelectFromHistory,
  onSetAnswerCheck,
  questionLanguage,
}: Props) {
  const [sidePanelFor, setSidePanelFor] = useState<Citation | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

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
          {onNavigate && (
            <span style={{ position: 'relative', display: 'inline-flex' }}>
              <button
                className="hamb"
                onClick={() => setMenuOpen((o) => !o)}
                aria-label="open surfaces menu"
                aria-expanded={menuOpen}
                title="surfaces"
              >
                ⊞
              </button>
              {menuOpen && (
                <div
                  role="menu"
                  style={{
                    position: 'absolute',
                    top: 'calc(100% + 6px)',
                    right: 0,
                    zIndex: 50,
                    minWidth: 160,
                    display: 'flex',
                    flexDirection: 'column',
                    background: 'var(--surface)',
                    border: '1px solid var(--hairline)',
                    borderRadius: 'var(--radius-sm)',
                    boxShadow: 'var(--shadow-2)',
                    overflow: 'hidden',
                  }}
                >
                  {SURVIVOR_NAV.map((s) => (
                    <button
                      key={s.id}
                      role="menuitem"
                      className="hamb"
                      style={{
                        textAlign: 'left',
                        padding: '9px 12px',
                        borderRadius: 0,
                        color: 'var(--ink)',
                        fontFamily: 'var(--font-ui)',
                        fontSize: 13,
                      }}
                      onClick={() => {
                        setMenuOpen(false)
                        onNavigate(s.id)
                      }}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              )}
            </span>
          )}
          {onSetProvider && (
            <ProviderSelector data={providers} onChange={onSetProvider} />
          )}
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
                language={questionLanguage}
              />
            )}
            {scene === 'writing' && (
              <FrameDynamic
                frame={{ question: streamingQuestion, blocks: partialBlocks }}
                onOpenCitation={setSidePanelFor}
                onAsk={onAsk}
                language={questionLanguage}
              />
            )}
            {scene === 'frame' && activeQuestion && (
              <>
                <FrameDynamic
                  frame={activeQuestion.frame}
                  onOpenCitation={setSidePanelFor}
                  onAsk={onAsk}
                  language={questionLanguage}
                />
                {(!activeQuestion.frame.status ||
                  activeQuestion.frame.status === 'answer' ||
                  activeQuestion.frame.status === 'legacy') && (
                  <AnswerCheck
                    value={activeQuestion.answer_check}
                    onSet={(v) => onSetAnswerCheck(activeQuestion.position, v)}
                    language={activeQuestion.frame.question_language ?? questionLanguage}
                  />
                )}
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
