import { useState } from 'react'
import type { CuadernoProvidersResponse } from '../../types/api'

type Props = {
  data: CuadernoProvidersResponse | null
  onChange: (provider: string, model: string) => void
}

export function ProviderSelector({ data, onChange }: Props) {
  const [open, setOpen] = useState(false)
  if (!data) return null

  const current = data.current.provider ?? data.providers[0]?.name ?? '—'
  const currentModel = data.current.model ?? ''

  return (
    <div className="cua-provider" style={{ position: 'relative' }}>
      <button
        className="provider-btn"
        onClick={() => setOpen((o) => !o)}
        aria-label="LLM provider"
        style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-2)' }}
      >
        {current}
        {currentModel ? ` · ${currentModel}` : ''}
      </button>
      {open && (
        <div
          className="provider-menu"
          style={{
            position: 'absolute', right: 0, top: '100%', zIndex: 20,
            background: 'var(--surface)', border: '1px solid var(--line)',
            padding: 8, fontFamily: 'var(--font-mono)', fontSize: 11, minWidth: 200,
          }}
        >
          {data.providers.map((p) => {
            const model = p.default_model ?? ''
            const disabled = !p.key_configured
            return (
              <button
                key={p.name}
                disabled={disabled}
                onClick={() => {
                  onChange(p.name, model)
                  setOpen(false)
                }}
                style={{
                  display: 'block', width: '100%', textAlign: 'left', padding: '4px 6px',
                  opacity: disabled ? 0.5 : 1, cursor: disabled ? 'not-allowed' : 'pointer',
                }}
                title={disabled ? 'API key not configured — open Settings' : ''}
              >
                {p.name}
                {model ? ` · ${model}` : ''}
                {disabled ? ' · no key' : ''}
              </button>
            )
          })}
          <div style={{ marginTop: 6, color: 'var(--ink-3)' }}>
            Keys: configure in Settings
          </div>
        </div>
      )}
    </div>
  )
}
