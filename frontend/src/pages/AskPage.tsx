import { useState, useRef, useEffect } from 'react'
import { api } from '../api/client'
import type { AskResponse, AdvisorConflict } from '../types/api'

// Import existing visual components to use them as "Artifacts" in the chat
import { ArchitecturePage } from './ArchitecturePage'
import { RisksPage } from './RisksPage'
import { AtlasPage } from './AtlasPage'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  loading?: boolean
  error?: string
  // Artifacts returned by the API
  toolUsed?: 'architecture' | 'risks' | 'atlas' | 'decisions'
  toolData?: any
  citations?: any[]
  conflicts?: AdvisorConflict[]
}

export function AskPage({ onNotify }: { onNotify?: (msg: string) => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([{
    id: 'welcome',
    role: 'assistant',
    text: "I am the project's consciousness. Ask me anything about the architecture, risks, or intent.",
  }])
  const [input, setInput] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || isTyping) return
    const userText = input.trim()
    setInput('')
    
    const userMsgId = Date.now().toString()
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', text: userText }])
    
    const loadingMsgId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: loadingMsgId, role: 'assistant', text: 'Thinking...', loading: true }])
    setIsTyping(true)

    try {
      const chatRes = await api.agentChat('scout', userText)
      
      let answer = chatRes.response
      let toolUsed: any = undefined
      let toolData: any = undefined

      // Check if response is JSON-encoded (it will be for artifacts)
      try {
        const parsed = JSON.parse(chatRes.response)
        if (parsed.tool_used) {
          answer = parsed.answer
          toolUsed = parsed.tool_used
          toolData = parsed.tool_data
        }
      } catch {
        // Not JSON, use as plain text
      }

      setMessages(prev => prev.map(m => m.id === loadingMsgId ? {
        ...m,
        text: answer,
        loading: false,
        toolUsed: toolUsed,
        toolData: toolData
      } : m))

    } catch (e) {
      setMessages(prev => prev.map(m => m.id === loadingMsgId ? {
        ...m,
        text: '',
        loading: false,
        error: e instanceof Error ? e.message : 'Failed to get answer'
      } : m))
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

  return (
    <div className="chat-container" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 120px)', background: 'var(--bg)', borderRadius: 8, overflow: 'hidden' }}>
      
      {/* Chat History */}
      <div className="chat-history" style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '32px' }}>
        {messages.map(msg => (
          <div key={msg.id} className={`chat-message role-${msg.role}`} style={{ display: 'flex', gap: '16px', maxWidth: '100%', alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            
            {/* Avatar */}
            {msg.role === 'assistant' && (
              <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--accent-cyan)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#000', fontWeight: 'bold', flexShrink: 0 }}>C</div>
            )}
            
            {/* Content Area */}
            <div style={{ display: 'grid', gap: '16px', width: msg.role === 'user' ? 'auto' : '100%' }}>
              
              {/* Text Bubble */}
              {msg.text && (
                <div style={{ 
                  background: msg.role === 'user' ? 'var(--accent-cyan)' : 'transparent', 
                  color: msg.role === 'user' ? '#000' : 'var(--text-primary)',
                  padding: msg.role === 'user' ? '12px 16px' : '0',
                  borderRadius: msg.role === 'user' ? '16px 16px 0 16px' : '0',
                  lineHeight: '1.6',
                  fontSize: '15px',
                  whiteSpace: 'pre-wrap'
                }}>
                  {msg.loading ? <span className="pulsing-cursor">●</span> : msg.text}
                </div>
              )}

              {/* Error State */}
              {msg.error && <div className="error" style={{ fontSize: 13, padding: 8 }}>{msg.error}</div>}

              {/* Dynamic Artifacts (GenUI Component Injection) */}
              {msg.toolUsed === 'architecture' && msg.toolData && (
                <div className="artifact-container" style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 16, background: '#111115' }}>
                  <div className="muted" style={{ marginBottom: 12, fontSize: 11 }}>// artifact: architecture_graph</div>
                  <ArchitecturePage nodes={msg.toolData.nodes} edges={msg.toolData.edges} />
                </div>
              )}

              {msg.toolUsed === 'risks' && msg.toolData && (
                <div className="artifact-container" style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 16, background: '#111115' }}>
                   <div className="muted" style={{ marginBottom: 12, fontSize: 11 }}>// artifact: risk_map</div>
                   <RisksPage items={msg.toolData} focusRiskArea={null} />
                </div>
              )}

              {msg.toolUsed === 'atlas' && msg.toolData && (
                <div className="artifact-container" style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 16, background: '#111115' }}>
                   <div className="muted" style={{ marginBottom: 12, fontSize: 11 }}>// artifact: project_overview</div>
                   <AtlasPage overview={msg.toolData.overview} changes={msg.toolData.changes} risks={msg.toolData.risks} decisions={msg.toolData.decisions} />
                </div>
              )}

              {/* Citations & Conflicts (Inline) */}
              {msg.conflicts && msg.conflicts.length > 0 && (
                <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid var(--accent-red)', borderRadius: 6, padding: 12, fontSize: 13 }}>
                  <strong style={{ color: 'var(--accent-red)' }}>Warning: Potential Intent Conflict</strong>
                  <ul style={{ margin: '8px 0 0 0', paddingLeft: 20 }}>
                    {msg.conflicts.map(c => <li key={c.decision_id} className="muted">{c.why_conflict}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input Area */}
      <div className="chat-input-area" style={{ padding: '24px', borderTop: '1px solid var(--border)', background: 'var(--bg-dark)' }}>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask project consciousness or request specific maps (e.g., 'show architecture')..."
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
              lineHeight: '1.5'
            }}
          />
          <button 
            onClick={handleSend} 
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
