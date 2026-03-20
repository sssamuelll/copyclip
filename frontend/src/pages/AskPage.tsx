import { useState, useRef, useEffect } from 'react'
import { api } from '../api/client'
import type { AdvisorConflict } from '../types/api'

import { ArchitecturePage } from './ArchitecturePage'
import { RisksPage } from './RisksPage'
import { AtlasPage } from './AtlasPage'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  loading?: boolean
  error?: string
  toolUsed?: 'architecture' | 'risks' | 'atlas' | 'decisions'
  toolData?: any
  citations?: any[]
  conflicts?: AdvisorConflict[]
}

export function AskPage({ onNotify }: { onNotify?: (msg: string) => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([{
    id: 'welcome',
    role: 'assistant',
    text: "I am the project's consciousness. Ask about architecture, intent, drift, risks, or the hidden shape of the system.",
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
    
    console.group(`%c[Consciousness] User: "${userText}"`, 'color: #3b82f6; font-weight: bold;')
    
    const userMsgId = Date.now().toString()
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', text: userText }])
    
    const loadingMsgId = (Date.now() + 1).toString()
    setMessages(prev => [...prev, { id: loadingMsgId, role: 'assistant', text: 'Consulting the consciousness…', loading: true }])
    setIsTyping(true)

    try {
      const chatRes = await api.agentChat('scout', userText)
      console.log('%cAgent Raw Response:', 'color: #9ca3af;', chatRes.response)
      
      let answer = chatRes.response
      let toolUsed: any = undefined
      let toolData: any = undefined

      try {
        const parsed = JSON.parse(chatRes.response)
        if (parsed.tool_used) {
          answer = parsed.answer
          toolUsed = parsed.tool_used
          toolData = parsed.tool_data
          console.log(`%c[GenUI] Injected Artifact: ${toolUsed}`, 'color: #f59e0b; font-weight: bold;', toolData)
        }
      } catch {
        console.log('%c[GenUI] No artifact detected, rendering plain text.', 'color: #6b7280;')
      }

      setMessages(prev => prev.map(m => m.id === loadingMsgId ? {
        ...m,
        text: answer,
        loading: false,
        toolUsed: toolUsed,
        toolData: toolData
      } : m))

    } catch (e) {
      console.error('%c[Consciousness Error]', 'color: #ef4444; font-weight: bold;', e)
      setMessages(prev => prev.map(m => m.id === loadingMsgId ? {
        ...m,
        text: '',
        loading: false,
        error: e instanceof Error ? e.message : 'Failed to get answer'
      } : m))
    } finally {
      setIsTyping(false)
      console.groupEnd()
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
      <div style={{ padding: '0 24px 12px 24px' }}>
        <div className="muted" style={{ fontSize: 10, letterSpacing: 2 }}>// consciousness_interface</div>
        <h1 style={{ margin: '8px 0 6px 0' }}>Ask the Consciousness</h1>
        <div className="muted" style={{ fontSize: 13, maxWidth: 720 }}>
          Interrogate the living state of the project. Ask about architecture, intent, drift, risk, and the hidden relationships shaping the system.
        </div>
      </div>
      
      <div className="chat-history" style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '32px' }}>
        {messages.map(msg => (
          <div key={msg.id} className={`chat-message role-${msg.role}`} style={{ display: 'flex', gap: '16px', maxWidth: '100%', alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
            
            {msg.role === 'assistant' && (
              <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--accent-cyan)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#000', fontWeight: 'bold', flexShrink: 0 }}>C</div>
            )}
            
            <div style={{ display: 'grid', gap: '16px', width: msg.role === 'user' ? 'auto' : '100%' }}>
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

              {msg.error && <div className="error" style={{ fontSize: 13, padding: 8 }}>{msg.error}</div>}

              {msg.toolUsed === 'architecture' && msg.toolData && (
                <div className="artifact-container" style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 16, background: '#111115' }}>
                  <div className="muted" style={{ marginBottom: 12, fontSize: 11 }}>// artifact: architecture_constellation</div>
                  <ArchitecturePage nodes={msg.toolData.nodes} edges={msg.toolData.edges} />
                </div>
              )}

              {msg.toolUsed === 'risks' && msg.toolData && (
                <div className="artifact-container" style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 16, background: '#111115' }}>
                   <div className="muted" style={{ marginBottom: 12, fontSize: 11 }}>// artifact: distortion_field</div>
                   <RisksPage items={msg.toolData} focusRiskArea={null} />
                </div>
              )}

              {msg.toolUsed === 'atlas' && msg.toolData && (
                <div className="artifact-container" style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 16, background: '#111115' }}>
                   <div className="muted" style={{ marginBottom: 12, fontSize: 11 }}>// artifact: atlas_projection</div>
                   <AtlasPage overview={msg.toolData.overview} changes={msg.toolData.changes} risks={msg.toolData.risks} decisions={msg.toolData.decisions} />
                </div>
              )}

              {msg.conflicts && msg.conflicts.length > 0 && (
                <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid var(--accent-red)', borderRadius: 6, padding: 12, fontSize: 13 }}>
                  <strong style={{ color: 'var(--accent-red)' }}>Oracle warning: anchored intent may be under tension</strong>
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

      <div className="chat-input-area" style={{ padding: '24px', borderTop: '1px solid var(--border)', background: 'var(--bg-dark)' }}>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about architecture, drift, intent, or the hidden shape of the system…"
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
