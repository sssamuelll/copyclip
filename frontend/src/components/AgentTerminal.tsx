import { useState } from 'react'
import { api } from '../api/client'

export function AgentTerminal() {
  const [isOpen, setIsOpen] = useState(false)
  const [agent, setAgent] = useState('scout')
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<{ role: 'user' | 'agent'; text: string }[]>([])
  const [loading, setLoading] = useState(false)

  const handleSend = async () => {
    if (!input.trim() || loading) return
    const userMsg = input
    setInput('')
    setMessages(prev => [...prev, { role: 'user', text: userMsg }])
    setLoading(true)
    
    try {
      const res = await api.agentChat(agent, userMsg)
      setMessages(prev => [...prev, { role: 'agent', text: res.response }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'agent', text: 'Error: Agent is offline or misconfigured.' }])
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) {
    return (
      <button 
        onClick={() => setIsOpen(true)}
        style={{
          position: 'fixed', bottom: '20px', right: '24px',
          background: 'var(--accent)', color: '#000', border: 'none',
          padding: '12px 24px', cursor: 'pointer', borderRadius: '4px',
          fontWeight: 'bold', boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
          zIndex: 1000
        }}
      >
        Talk to Agents
      </button>
    )
  }

  return (
    <div style={{
      position: 'fixed', bottom: '20px', right: '24px',
      width: '400px', height: '500px', background: 'var(--panel)',
      border: '1px solid var(--accent)', borderRadius: '8px',
      display: 'flex', flexDirection: 'column', zIndex: 1000,
      boxShadow: '0 8px 24px rgba(0,0,0,0.8)'
    }}>
      <div style={{ padding: '12px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <select 
          value={agent} 
          onChange={e => setAgent(e.target.value)}
          style={{ background: 'transparent', color: 'var(--accent)', border: 'none', fontWeight: 'bold' }}
        >
          <option value="scout">The Scout</option>
          <option value="critic">The Critic</option>
          <option value="historian">The Historian</option>
        </select>
        <button onClick={() => setIsOpen(false)} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer' }}>_</button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {messages.length === 0 && (
          <div className="muted" style={{ fontSize: '0.8rem', textAlign: 'center', marginTop: '2rem' }}>
            Ask me anything about the codebase, its history, or architectural rules.
          </div>
        )}
        {messages.map((m, idx) => (
          <div key={idx} style={{ 
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '85%',
            background: m.role === 'user' ? '#333' : 'rgba(16, 185, 129, 0.1)',
            padding: '8px 12px', borderRadius: '8px', fontSize: '0.9rem',
            whiteSpace: 'pre-wrap'
          }}>
            {m.text}
          </div>
        ))}
        {loading && <div className="muted" style={{ fontSize: '0.8rem' }}>{agent} is thinking...</div>}
      </div>

      <div style={{ padding: '12px', borderTop: '1px solid var(--border)', display: 'flex', gap: '8px' }}>
        <input 
          type="text" 
          placeholder="Ask agent..." 
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          style={{ flex: 1, background: '#000', border: '1px solid var(--border)', color: '#fff', padding: '8px', borderRadius: '4px' }}
        />
        <button className="btn primary" onClick={handleSend} disabled={loading} style={{ padding: '8px' }}>Send</button>
      </div>
    </div>
  )
}
