import { useEffect, useState } from 'react'
import { api } from '../api/client'

export function SettingsPage({ onNotify }: { onNotify?: (msg: string) => void }) {
  const [config, setConfig] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.getConfig().then(setConfig)
  }, [])

  const handleChange = (key: string, value: string) => {
    setConfig(prev => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  const handleSave = async () => {
    setLoading(true)
    try {
      await api.setConfig(config)
      setSaved(true)
      onNotify?.('Settings saved')
      setTimeout(() => setSaved(false), 3000)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="page">
      <h2>Project Settings</h2>
      <p className="muted">Configure AI providers and project preferences. Settings are stored locally in .copyclip/</p>

      <div className="panel" style={{ marginTop: '2rem', maxWidth: '600px' }}>
        <h3>LLM Configuration</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', marginTop: '1rem' }}>
          
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', marginBottom: '0.5rem', opacity: 0.7 }}>Active Provider</label>
            <select 
              value={config['COPYCLIP_LLM_PROVIDER'] || ''} 
              onChange={e => handleChange('COPYCLIP_LLM_PROVIDER', e.target.value)}
              style={{ width: '100%', background: '#000', color: '#fff', border: '1px solid var(--border)', padding: '8px' }}
            >
              <option value="">Select a provider...</option>
              <option value="openai">OpenAI (GPT-4o, etc.)</option>
              <option value="anthropic">Anthropic (Claude 3.5)</option>
              <option value="gemini">Google Gemini</option>
              <option value="deepseek">DeepSeek</option>
              <option value="openrouter">OpenRouter / OpenClaw</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', marginBottom: '0.5rem', opacity: 0.7 }}>OpenAI API Key</label>
            <input 
              type="password" 
              value={config['OPENAI_API_KEY'] || ''} 
              onChange={e => handleChange('OPENAI_API_KEY', e.target.value)}
              placeholder="sk-..."
              style={{ width: '100%', background: '#000', color: '#fff', border: '1px solid var(--border)', padding: '8px' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', marginBottom: '0.5rem', opacity: 0.7 }}>Anthropic API Key</label>
            <input 
              type="password" 
              value={config['ANTHROPIC_API_KEY'] || ''} 
              onChange={e => handleChange('ANTHROPIC_API_KEY', e.target.value)}
              placeholder="sk-ant-..."
              style={{ width: '100%', background: '#000', color: '#fff', border: '1px solid var(--border)', padding: '8px' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', marginBottom: '0.5rem', opacity: 0.7 }}>Gemini API Key</label>
            <input 
              type="password" 
              value={config['GEMINI_API_KEY'] || ''} 
              onChange={e => handleChange('GEMINI_API_KEY', e.target.value)}
              style={{ width: '100%', background: '#000', color: '#fff', border: '1px solid var(--border)', padding: '8px' }}
            />
          </div>

          <div style={{ borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
            <button 
              className="btn primary" 
              onClick={handleSave} 
              disabled={loading}
            >
              {loading ? 'Saving...' : saved ? 'SETTINGS SAVED!' : 'Save Configuration'}
            </button>
          </div>

        </div>
      </div>
    </section>
  )
}
