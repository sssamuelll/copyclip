import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { AlertEvent, AlertRule, WeeklyExport } from '../types/api'

export function OpsPage() {
  const [rules, setRules] = useState<AlertRule[]>([])
  const [events, setEvents] = useState<AlertEvent[]>([])
  const [fired, setFired] = useState<string[]>([])
  const [brief, setBrief] = useState<WeeklyExport | null>(null)
  const [days, setDays] = useState(7)

  const [newRule, setNewRule] = useState({
    name: 'custom-risk-rule',
    kind: '',
    severity: '',
    min_score: 70,
    cooldown_min: 60,
  })

  const refresh = async () => {
    const [alertsRes, rulesRes] = await Promise.all([api.alerts(), api.alertRules()])
    setRules(rulesRes.items || [])
    setEvents(alertsRes.events || [])
    setFired((alertsRes.fired || []).map((f) => f.title))
  }

  useEffect(() => {
    refresh().catch(() => {})
  }, [])

  const onCreateRule = async () => {
    await api.upsertAlertRule({
      ...newRule,
      kind: newRule.kind || undefined,
      severity: newRule.severity || undefined,
      enabled: true,
    })
    await refresh()
  }

  const onGenerateBrief = async () => {
    const res = await api.weeklyExport(days)
    setBrief(res)
  }

  return (
    <section>
      <h2>ops center</h2>

      <div className="panel" style={{ marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>alert rules</h3>
        <div style={{ display: 'grid', gap: 8, gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr auto' }}>
          <input value={newRule.name} onChange={(e) => setNewRule({ ...newRule, name: e.target.value })} placeholder="name" />
          <input value={newRule.kind} onChange={(e) => setNewRule({ ...newRule, kind: e.target.value })} placeholder="kind (optional)" />
          <input value={newRule.severity} onChange={(e) => setNewRule({ ...newRule, severity: e.target.value })} placeholder="severity (optional)" />
          <input type="number" value={newRule.min_score} onChange={(e) => setNewRule({ ...newRule, min_score: Number(e.target.value) })} placeholder="min_score" />
          <input type="number" value={newRule.cooldown_min} onChange={(e) => setNewRule({ ...newRule, cooldown_min: Number(e.target.value) })} placeholder="cooldown_min" />
          <button onClick={onCreateRule}>Save</button>
        </div>
        <ul>
          {rules.map((r) => (
            <li key={r.id}>
              {r.name} — kind:{r.kind || '*'} severity:{r.severity || '*'} score≥{r.min_score} cooldown:{r.cooldown_min}m
            </li>
          ))}
        </ul>
      </div>

      <div className="panel" style={{ marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>alerts</h3>
        <button onClick={refresh}>Evaluate now</button>
        {fired.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <strong>New fired:</strong>
            <ul>{fired.map((f, i) => <li key={i}>{f}</li>)}</ul>
          </div>
        )}
        <ul>
          {events.map((e) => (
            <li key={e.id}>[{e.created_at?.slice(0, 19)}] {e.title} — {e.detail}</li>
          ))}
        </ul>
      </div>

      <div className="panel">
        <h3 style={{ marginTop: 0 }}>weekly executive brief</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input type="number" value={days} onChange={(e) => setDays(Number(e.target.value) || 7)} style={{ width: 80 }} />
          <button onClick={onGenerateBrief}>Generate brief</button>
        </div>
        {brief && (
          <>
            <pre style={{ whiteSpace: 'pre-wrap', marginTop: 12 }}>{brief.markdown}</pre>
            <button onClick={() => navigator.clipboard?.writeText(brief.markdown)}>Copy markdown</button>
          </>
        )}
      </div>
    </section>
  )
}
