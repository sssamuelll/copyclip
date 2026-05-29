import { useEffect } from 'react'
import type { CuadernoQuestion } from '../../types/api'

type Props = {
  questions: CuadernoQuestion[]
  activePosition: number | null
  onSelect: (position: number) => void
  onClose: () => void
}

export function HistoryOverlay({ questions, activePosition, onSelect, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <>
      <div className="history-back" onClick={onClose} />
      <div className="history">
        <div className="history-head">
          <span>session · this conversation</span>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 0,
              color: 'var(--ink-3)',
              cursor: 'pointer',
              fontSize: 14,
            }}
          >
            esc
          </button>
        </div>
        <div className="history-list">
          {questions.map((q) => (
            <button
              key={q.position}
              className={
                'h-item' +
                (q.bookmarked ? ' bookmarked' : '') +
                (q.position === activePosition ? ' active' : '')
              }
              onClick={() => onSelect(q.position)}
            >
              <span className="num">{String(q.position).padStart(2, '0')}</span>
              <span className="q">{q.question}</span>
              <span className="when">{q.created_at}</span>
            </button>
          ))}
        </div>
      </div>
    </>
  )
}
