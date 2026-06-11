import { useState } from 'react'
import { api } from '../../api/client'

type Action = { decision_id: number; to_status: string }

// The cuaderno's ONLY write. The tutor merely PROPOSES a decision status change
// (a callout's decision_action); the human's click here performs the PATCH. The
// model is never in the write loop — it exposes, the human authors.
export function DecisionConfirm({ action, lang }: { action: Action; lang?: string | null }) {
  const [state, setState] = useState<'idle' | 'saving' | 'done' | 'error'>('idle')
  const [err, setErr] = useState('')
  const en = lang === 'en'
  const target = `#${action.decision_id} → ${action.to_status}`

  async function confirm() {
    setState('saving')
    setErr('')
    try {
      await api.updateDecisionStatus(action.decision_id, action.to_status)
      setState('done')
    } catch (e: any) {
      setErr(e?.message || (en ? 'could not apply' : 'no se pudo aplicar'))
      setState('error')
    }
  }

  if (state === 'done') {
    return (
      <div className="decision-confirm done">
        ✓ {en ? 'applied' : 'aplicado'} {target}
      </div>
    )
  }

  return (
    <div className="decision-confirm">
      <button className="decision-confirm-btn" disabled={state === 'saving'} onClick={confirm}>
        {state === 'saving'
          ? en ? 'applying…' : 'aplicando…'
          : `${en ? 'confirm' : 'confirmar'} ${target}`}
      </button>
      {state === 'error' ? <span className="decision-confirm-err">{err}</span> : null}
    </div>
  )
}
