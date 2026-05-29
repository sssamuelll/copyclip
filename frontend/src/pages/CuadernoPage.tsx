import { useEffect, useMemo, useRef, useState } from 'react'
import type { Block, CuadernoQuestion, ToolRow, CuadernoProvidersResponse } from '../types/api'
import { Cuaderno } from '../components/cuaderno/Cuaderno'
import { askStream, cuadernoApi } from '../api/cuaderno'

const SESSION_STORAGE_KEY = 'copyclip.cuaderno.session_id'

export function CuadernoPage({ onOpenDashboard }: { onOpenDashboard?: () => void } = {}) {
  const [sessionId, setSessionId] = useState<string | null>(() =>
    localStorage.getItem(SESSION_STORAGE_KEY),
  )
  const [questions, setQuestions] = useState<CuadernoQuestion[]>([])
  const [activePosition, setActivePosition] = useState<number | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [providers, setProviders] = useState<CuadernoProvidersResponse | null>(null)
  const [streamingQuestion, setStreamingQuestion] = useState('')
  const [partialBlocks, setPartialBlocks] = useState<Block[]>([])
  const [toolCalls, setToolCalls] = useState<ToolRow[]>([])
  const abortRef = useRef<AbortController | null>(null)

  // Abort an in-flight stream on unmount.
  useEffect(() => () => abortRef.current?.abort(), [])

  const activeQuestion = useMemo(
    () => questions.find((q) => q.position === activePosition) ?? null,
    [questions, activePosition],
  )

  // Restore session on mount
  useEffect(() => {
    if (!sessionId) return
    cuadernoApi
      .session(sessionId)
      .then((s) => {
        setQuestions(s.questions)
        if (s.questions.length > 0) {
          setActivePosition(s.questions[s.questions.length - 1].position)
        }
      })
      .catch(() => {
        // session is dead; clear and start fresh
        localStorage.removeItem(SESSION_STORAGE_KEY)
        setSessionId(null)
      })
  }, [sessionId])

  // Load the provider list / current selection once on mount.
  useEffect(() => {
    cuadernoApi.providers().then(setProviders).catch(() => {})
  }, [])

  const onSetProvider = (provider: string, model: string) => {
    cuadernoApi.setProvider(provider, model).catch(() => {})
    setProviders((prev) =>
      prev ? { ...prev, current: { provider, model } } : prev,
    )
  }

  const onAsk = (question: string) => {
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac

    setError(null)
    setIsLoading(true)
    setStreamingQuestion(question)
    setPartialBlocks([])
    setToolCalls([])

    let capturedSession = sessionId

    askStream(question, sessionId ?? undefined, {
      signal: ac.signal,
      onEvent: (e) => {
        switch (e.type) {
          case 'meta':
            if (!capturedSession) {
              capturedSession = e.session_id
              setSessionId(e.session_id)
              localStorage.setItem(SESSION_STORAGE_KEY, e.session_id)
            }
            break
          case 'tool':
            setToolCalls((prev) => {
              const key = `${e.name} ${e.args}`
              const next = prev.filter((t) => `${t.name} ${t.args}` !== key)
              return [
                ...next,
                { state: e.state, name: e.name, args: e.args, ms: e.ms },
              ]
            })
            break
          case 'block':
            setPartialBlocks((prev) => [...prev, e.block])
            break
          case 'frame': {
            const newQ: CuadernoQuestion = {
              position: e.position,
              question,
              frame: e.frame,
              bookmarked: false,
              got_it: null,
              created_at: new Date().toISOString(),
            }
            setQuestions((prev) => [...prev, newQ])
            setActivePosition(e.position)
            break
          }
          case 'error':
            setError(e.partial ? `${e.message} (partial answer saved)` : e.message)
            break
        }
      },
    })
      .catch((err) => {
        if (ac.signal.aborted) return
        setError(String(err))
      })
      .finally(() => {
        if (ac.signal.aborted) return
        setIsLoading(false)
        setPartialBlocks([])
        setToolCalls([])
      })
  }

  const onSelectFromHistory = (position: number) => {
    setActivePosition(position)
  }

  const onSetGotIt = (position: number, value: 'got' | 'didnt') => {
    if (!sessionId) return
    cuadernoApi
      .patchQuestion(sessionId, position, { got_it: value })
      .catch(() => {})
    setQuestions((prev) =>
      prev.map((q) => (q.position === position ? { ...q, got_it: value } : q)),
    )
  }

  const sessionLabel = sessionId
    ? `session ${sessionId.slice(0, 8)}`
    : 'new session'
  const questionNumber = activePosition
    ? `${String(activePosition).padStart(2, '0')} · q`
    : '· q'

  return (
    <>
      {error ? (
        <div style={{
          background: 'var(--accent-soft)',
          color: 'var(--accent-ink)',
          padding: '8px 16px',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
        }}>
          {error}
        </div>
      ) : null}
      <Cuaderno
        sessionLabel={sessionLabel}
        questionNumber={questionNumber}
        questions={questions}
        activeQuestion={activeQuestion}
        isLoading={isLoading}
        streamingQuestion={streamingQuestion}
        partialBlocks={partialBlocks}
        toolCalls={toolCalls}
        providers={providers}
        onSetProvider={onSetProvider}
        onOpenDashboard={onOpenDashboard}
        onAsk={onAsk}
        onSelectFromHistory={onSelectFromHistory}
        onSetGotIt={onSetGotIt}
      />
    </>
  )
}
