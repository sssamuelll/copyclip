import { useEffect, useState } from 'react'
import { api } from '../api/client'

const paperWrap: React.CSSProperties = {
  background: 'var(--paper)',
  color: 'var(--ink)',
  fontFamily: 'var(--font-ui)',
  border: '1px solid var(--hairline)',
  borderRadius: 'var(--radius)',
  padding: '28px 32px',
  marginTop: '2rem',
  maxWidth: '600px',
  boxShadow: 'var(--shadow-1)',
}

const fieldLabel: React.CSSProperties = {
  display: 'block',
  fontFamily: 'var(--font-ui)',
  fontSize: '11px',
  textTransform: 'uppercase',
  letterSpacing: '0.14em',
  color: 'var(--ink-3)',
  marginBottom: '6px',
}

const fieldControl: React.CSSProperties = {
  width: '100%',
  background: 'var(--surface)',
  color: 'var(--ink)',
  border: '1px solid var(--hairline)',
  borderRadius: 'var(--radius-sm)',
  padding: '8px 10px',
  fontFamily: 'var(--font-ui)',
  fontSize: '14px',
  outline: 'none',
  boxSizing: 'border-box',
}

export function SettingsPage({ onNotify }: { onNotify?: (msg: string) => void }) {
  const [config, setConfig] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)

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

  // The analyze trigger lives here now (DebtNavigatorPage, which used to hold it,
  // dies in Wave 5). The job runs in the background — non-blocking — and notifies
  // here (toast) and in the CLI (server console).
  const handleAnalyze = async () => {
    setAnalyzing(true)
    try {
      const res = await api.startAnalyzeJob()
      onNotify?.(
        res.already_running
          ? 'Analysis already running — it continues in the background'
          : 'Analysis started — runs in the background; this can take a couple of minutes',
      )
    } catch {
      onNotify?.('Could not start analysis — check the server logs')
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <section className="page">
      <h2>Settings</h2>
      <p className="muted">Configure the LLM provider and API keys. Settings are stored locally inside .copyclip/.</p>

      <div style={paperWrap}>
        <h3 style={{ fontFamily: 'var(--font-ui)', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.16em', color: 'var(--ink-3)', margin: '0 0 20px 0', fontWeight: 500 }}>Providers</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

          <div>
            <label style={fieldLabel}>Active Provider</label>
            <select
              value={config['COPYCLIP_LLM_PROVIDER'] || ''}
              onChange={e => handleChange('COPYCLIP_LLM_PROVIDER', e.target.value)}
              style={fieldControl}
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
            <label style={fieldLabel}>OpenAI API Key</label>
            <input
              type="password"
              value={config['OPENAI_API_KEY'] || ''}
              onChange={e => handleChange('OPENAI_API_KEY', e.target.value)}
              placeholder="sk-..."
              style={fieldControl}
            />
          </div>

          <div>
            <label style={fieldLabel}>Anthropic API Key</label>
            <input
              type="password"
              value={config['ANTHROPIC_API_KEY'] || ''}
              onChange={e => handleChange('ANTHROPIC_API_KEY', e.target.value)}
              placeholder="sk-ant-..."
              style={fieldControl}
            />
          </div>

          <div>
            <label style={fieldLabel}>Gemini API Key</label>
            <input
              type="password"
              value={config['GEMINI_API_KEY'] || ''}
              onChange={e => handleChange('GEMINI_API_KEY', e.target.value)}
              style={fieldControl}
            />
          </div>

          <div style={{ borderTop: '1px solid var(--hairline)', paddingTop: '1rem' }}>
            <button
              className="btn primary"
              onClick={handleSave}
              disabled={loading}
            >
              {loading ? 'Saving…' : saved ? 'Saved' : 'Save'}
            </button>
          </div>

        </div>
      </div>

      <div style={paperWrap}>
        <h3 style={{ fontFamily: 'var(--font-ui)', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.16em', color: 'var(--ink-3)', margin: '0 0 14px 0', fontWeight: 500 }}>Analysis</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Re-index the project — dependency graph, churn, decisions, heat. Runs in
          the background, so you can keep working; progress shows here and in the CLI.
        </p>
        <div style={{ borderTop: '1px solid var(--hairline)', paddingTop: '1rem' }}>
          <button className="btn primary" onClick={handleAnalyze} disabled={analyzing}>
            {analyzing ? 'Starting…' : 'Re-analyze project'}
          </button>
        </div>
      </div>
    </section>
  )
}
