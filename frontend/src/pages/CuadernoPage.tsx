import { useEffect, useMemo, useState } from 'react'
import type { CuadernoQuestion } from '../types/api'
import { Cuaderno } from '../components/cuaderno/Cuaderno'
import { cuadernoApi } from '../api/cuaderno'

const SESSION_STORAGE_KEY = 'copyclip.cuaderno.session_id'

export function CuadernoPage() {
  const [sessionId, setSessionId] = useState<string | null>(() =>
    localStorage.getItem(SESSION_STORAGE_KEY),
  )
  const [questions, setQuestions] = useState<CuadernoQuestion[]>([])
  const [activePosition, setActivePosition] = useState<number | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  const onAsk = (question: string) => {
    setIsLoading(true)
    setError(null)
    cuadernoApi
      .ask(question, sessionId ?? undefined)
      .then((r) => {
        if (!sessionId) {
          setSessionId(r.session_id)
          localStorage.setItem(SESSION_STORAGE_KEY, r.session_id)
        }
        const newQ: CuadernoQuestion = {
          position: r.position,
          question,
          frame: r.frame,
          bookmarked: false,
          got_it: null,
          created_at: new Date().toISOString(),
        }
        setQuestions((prev) => [...prev, newQ])
        setActivePosition(r.position)
      })
      .catch((e) => setError(String(e)))
      .finally(() => setIsLoading(false))
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
        onAsk={onAsk}
        onSelectFromHistory={onSelectFromHistory}
        onSetGotIt={onSetGotIt}
      />
    </>
  )
}
