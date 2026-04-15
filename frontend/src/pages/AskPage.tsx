import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { AskEvidenceItem, AskResponse } from '../types/api'

type AskMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  response?: AskResponse
  loading?: boolean
  error?: string
}

export function AskPage({
  onNotify,
  onOpenDecision,
  onOpenRisk,
  onOpenChanges,
}: {
  onNotify?: (msg: string) => void
  onOpenDecision?: (id: number) => void
  onOpenRisk?: (area: string) => void
  onOpenChanges?: (opts?: { commitId?: string | null; filePath?: string | null }) => void
}) {
  const [messages, setMessages] = useState<AskMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: 'Ask Project now answers with evidence, confidence, and drill-down paths instead of generic chat.',
    },
  ])
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async (prefill?: string) => {
    const userText = (prefill ?? input).trim()
    if (!userText || isTyping) return
    setInput('')

    const userMsgId = Date.now().toString()
    setMessages((prev) => [...prev, { id: userMsgId, role: 'user', text: userText }])

    const loadingMsgId = `${Date.now()}-loading`
    setMessages((prev) => [...prev, { id: loadingMsgId, role: 'assistant', text: 'Investigating project evidence…', loading: true }])
    setIsTyping(true)

    try {
      const response = await api.ask(userText)
      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingMsgId
            ? {
                ...m,
                text: response.answer_summary || response.answer,
                response,
                loading: false,
              }
            : m,
        ),
      )
    } catch (e) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingMsgId
            ? {
                ...m,
                text: '',
                loading: false,
                error: e instanceof Error ? e.message : 'Failed to get answer',
              }
            : m,
        ),
      )
    } finally {
      setIsTyping(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const openEvidence = (item: AskEvidenceItem) => {
    const ref = item.ref
    if (ref.type === 'decision' && typeof ref.target === 'number') {
      onOpenDecision?.(ref.target)
      return
    }
    if (ref.type === 'risk') {
      const target = item.related_file || String(ref.target)
      onOpenRisk?.(target)
      return
    }
    if (ref.type === 'commit') {
      onOpenChanges?.({ commitId: String(ref.target) })
      return
    }
    if (ref.type === 'file') {
      onOpenChanges?.({ filePath: String(ref.target) })
      return
    }
    if (ref.type === 'symbol' && item.related_file) {
      onOpenChanges?.({ filePath: item.related_file })
      return
    }
    onNotify?.('No drill-down available for this evidence yet.')
  }

  return (
    <div className="chat-container" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 120px)', background: 'var(--bg)', borderRadius: 8, overflow: 'hidden' }}>
      <div style={{ padding: '0 24px 12px 24px' }}>
        <div className="muted" style={{ fontSize: 10, letterSpacing: 2 }}>// ask_project_investigation</div>
        <h1 style={{ margin: '8px 0 6px 0' }}>Ask Project</h1>
        <div className="muted" style={{ fontSize: 13, maxWidth: 760 }}>
          Ask about decisions, risks, commits, files, and symbols. The answer comes first, but the evidence, confidence, unknowns, and next drill-down paths stay visible.
        </div>
      </div>

      <div className="chat-history" style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {messages.map((msg) => (
          <div key={msg.id} style={{ display: 'grid', gap: '12px', alignSelf: msg.role === 'user' ? 'flex-end' : 'stretch' }}>
            {msg.role === 'user' ? (
              <div style={{ background: 'var(--accent-cyan)', color: '#000', padding: '12px 16px', borderRadius: '16px 16px 0 16px', maxWidth: 720 }}>
                {msg.text}
              </div>
            ) : (
              <div className="section-panel" style={{ display: 'grid', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <span className="muted" style={{ fontSize: 11 }}>// investigation_result</span>
                  {msg.response && <span className={`badge badge-${msg.response.confidence === 'high' ? 'high' : msg.response.confidence === 'medium' ? 'med' : 'low'}`}>{msg.response.confidence}</span>}
                  {msg.response && <span className="badge">{msg.response.answer_kind.replace('_', ' ')}</span>}
                </div>

                <div style={{ fontSize: 16, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                  {msg.loading ? <span className="pulsing-cursor">●</span> : msg.text}
                </div>

                {msg.error && <div className="error" style={{ fontSize: 13, padding: 8 }}>{msg.error}</div>}

                {msg.response && (
                  <>
                    <div style={{ display: 'grid', gap: 12 }}>
                      <Section title="// evidence_selection_rationale">
                        <ul style={{ margin: 0, paddingLeft: 18 }}>
                          {msg.response.evidence_selection_rationale.map((item, idx) => (
                            <li key={idx} className="muted">{item}</li>
                          ))}
                        </ul>
                      </Section>

                      <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
                        <EvidenceGroup title="decisions" items={msg.response.evidence.decisions} onOpen={openEvidence} />
                        <EvidenceGroup title="risks" items={msg.response.evidence.risks} onOpen={openEvidence} />
                        <EvidenceGroup title="files" items={msg.response.evidence.files} onOpen={openEvidence} />
                        <EvidenceGroup title="commits" items={msg.response.evidence.commits} onOpen={openEvidence} />
                        <EvidenceGroup title="symbols" items={msg.response.evidence.symbols} onOpen={openEvidence} />
                      </div>

                      <Section title="// gaps_or_unknowns">
                        {msg.response.gaps_or_unknowns.length ? (
                          <ul style={{ margin: 0, paddingLeft: 18 }}>
                            {msg.response.gaps_or_unknowns.map((item, idx) => (
                              <li key={idx} className="muted">{item}</li>
                            ))}
                          </ul>
                        ) : (
                          <div className="muted">No major evidence gaps surfaced for this answer.</div>
                        )}
                      </Section>

                      <Section title="// follow_up_questions">
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          {msg.response.next_questions.map((q, idx) => (
                            <button key={idx} className="btn" onClick={() => handleSend(q)}>{q}</button>
                          ))}
                        </div>
                      </Section>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-area" style={{ padding: '24px', borderTop: '1px solid var(--border)', background: 'var(--bg-dark)' }}>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about a decision, file, risk, commit, or symbol…"
            rows={1}
            disabled={isTyping}
            style={{
              width: '100%',
              background: 'transparent',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
              borderRadius: 24,
              padding: '16px 24px',
              paddingRight: '60px',
              fontSize: '15px',
              resize: 'none',
              overflow: 'hidden',
              lineHeight: '1.5',
            }}
          />
          <button
            onClick={() => handleSend()}
            disabled={!input.trim() || isTyping}
            style={{ position: 'absolute', right: 8, background: 'var(--accent-cyan)', color: '#000', border: 'none', borderRadius: '50%', width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', opacity: input.trim() ? 1 : 0.5 }}
          >
            ↑
          </button>
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="insight-card" style={{ margin: 0 }}>
      <div className="insight-title">{title}</div>
      <div style={{ marginTop: 8 }}>{children}</div>
    </div>
  )
}

function EvidenceGroup({ title, items, onOpen }: { title: string; items: AskEvidenceItem[]; onOpen: (item: AskEvidenceItem) => void }) {
  return (
    <Section title={`// ${title}`}>
      {items.length ? (
        <div style={{ display: 'grid', gap: 8 }}>
          {items.map((item) => (
            <div key={item.evidence_id} className="panel" style={{ padding: 10, display: 'grid', gap: 6 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <strong>{item.label}</strong>
                <span className="badge">score {Math.round(item.score)}</span>
                <button className="btn" style={{ marginLeft: 'auto' }} onClick={() => onOpen(item)}>open</button>
              </div>
              {item.snippet && <div className="muted" style={{ fontSize: 12 }}>{item.snippet}</div>}
              {item.related_file && <div className="muted" style={{ fontSize: 11 }}>related file: {item.related_file}</div>}
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {item.why_selected.map((why, idx) => (
                  <li key={idx} className="muted">{why}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : (
        <div className="muted">No {title} evidence selected.</div>
      )}
    </Section>
  )
}
