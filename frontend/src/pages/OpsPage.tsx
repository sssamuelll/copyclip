import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { AlertEvent, AlertRule, WeeklyExport, SchedulerState, AnalyzeJob } from '../types/api'

export function OpsPage({ onNotify }: { onNotify?: (msg: string) => void }) {
  const [rules, setRules] = useState<AlertRule[]>([])
  const [events, setEvents] = useState<AlertEvent[]>([])
  const [fired, setFired] = useState<string[]>([])
  const [brief, setBrief] = useState<WeeklyExport | null>(null)
  const [days, setDays] = useState(7)
  const [scheduler, setScheduler] = useState<SchedulerState | null>(null)
  const [analysisJobs, setAnalysisJobs] = useState<AnalyzeJob[]>([])

  const [newRule, setNewRule] = useState({
    name: 'custom-risk-rule',
    kind: '',
    severity: '',
    min_score: 70,
    cooldown_min: 60,
  })

  const refresh = async () => {
    const [alertsRes, rulesRes, schedulerRes, jobsRes] = await Promise.all([api.alerts(), api.alertRules(), api.schedulerState(), api.analyzeStatus()])
    setRules(rulesRes.items || [])
    setEvents(alertsRes.events || [])
    setFired((alertsRes.fired || []).map((f) => f.title))
    setScheduler(schedulerRes)
    setAnalysisJobs(jobsRes.items || [])
  }

  useEffect(() => {
    refresh().catch(() => {})
  }, [])

  useEffect(() => {
    const t = window.setInterval(() => {
      api.analyzeStatus().then((jobsRes) => setAnalysisJobs(jobsRes.items || [])).catch(() => {})
    }, 1500)
    return () => window.clearInterval(t)
  }, [])

  const onStartAnalyze = async () => {
    const res = await api.startAnalyzeJob()
    await refresh()
    onNotify?.(res.already_running ? 'Analyze already running' : 'Analyze job started')
  }

  const onResumeAnalyze = async () => {
    try {
      const res = await api.resumeAnalyzeJob()
      await refresh()
      onNotify?.(res.already_running ? 'Analyze already running' : `Analyze resumed${res.resume_from != null ? ` from ${res.resume_from}` : ''}`)
    } catch (e: any) {
      onNotify?.(`Resume failed: ${e?.message || 'unknown error'}`)
    }
  }

  const onCreateRule = async () => {
    await api.upsertAlertRule({
      ...newRule,
      kind: newRule.kind || undefined,
      severity: newRule.severity || undefined,
      enabled: true,
    })
    await refresh()
    onNotify?.('Rule saved')
  }

  const onToggleRule = async (rule: AlertRule) => {
    await api.updateAlertRule(rule.id, { enabled: !rule.enabled })
    await refresh()
    onNotify?.(rule.enabled ? 'Rule disabled' : 'Rule enabled')
  }

  const onEditRule = async (rule: AlertRule) => {
    const minScore = Number(prompt('min_score', String(rule.min_score)) || rule.min_score)
    const cooldown = Number(prompt('cooldown_min', String(rule.cooldown_min)) || rule.cooldown_min)
    const kind = prompt('kind (blank for any)', rule.kind || '') ?? rule.kind ?? ''
    const severity = prompt('severity (blank for any)', rule.severity || '') ?? rule.severity ?? ''
    await api.updateAlertRule(rule.id, {
      min_score: minScore,
      cooldown_min: cooldown,
      kind: kind || '',
      severity: severity || '',
    })
    await refresh()
    onNotify?.('Rule updated')
  }

  const onDeleteRule = async (rule: AlertRule) => {
    if (!confirm(`Delete rule '${rule.name}'?`)) return
    await api.deleteAlertRule(rule.id)
    await refresh()
    onNotify?.('Rule deleted')
  }

  const onGenerateBrief = async () => {
    const res = await api.weeklyExport(days)
    setBrief(res)
  }

  const onToggleScheduler = async () => {
    if (!scheduler) return
    await api.setSchedulerState({ enabled: !scheduler.enabled })
    await refresh()
    onNotify?.(scheduler.enabled ? 'Scheduler disabled' : 'Scheduler enabled')
  }

  const onSetSchedulerInterval = async () => {
    if (!scheduler) return
    const value = Number(prompt('Scheduler interval (seconds)', String(scheduler.interval_sec)) || scheduler.interval_sec)
    await api.setSchedulerState({ interval_sec: value })
    await refresh()
    onNotify?.('Scheduler interval updated')
  }

  const activeJob = analysisJobs.find((j) => j.status === 'running' || j.status === 'queued') || null
  const latestJob = analysisJobs[0] || null
  const progressRatio = activeJob && activeJob.total > 0 ? Math.min(1, Math.max(0, activeJob.processed / activeJob.total)) : 0
  const progressPct = Math.round(progressRatio * 100)

  return (
    <section>
      <h2>ops center</h2>

      <div className="panel" style={{ marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>project analyze</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button onClick={onStartAnalyze}>Start incremental analyze</button>
          <button onClick={onResumeAnalyze}>Resume last failed job</button>
          {activeJob ? (
            <span>
              {activeJob.status} / {activeJob.phase || 'analyzing'} — {activeJob.processed}/{activeJob.total}
              {activeJob.throughput_fps != null ? ` • ${activeJob.throughput_fps} files/s` : ''}
              {activeJob.eta_sec != null ? ` • ETA ${activeJob.eta_sec}s` : ''}
            </span>
          ) : (
            <span className="muted">No active analyze job.</span>
          )}
        </div>

        <div style={{ marginTop: 10 }}>
          <div style={{ height: 8, width: '100%', borderRadius: 8, background: 'var(--panel-2, #222)', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${progressPct}%`, background: 'var(--accent, #4f8cff)', transition: 'width 150ms linear' }} />
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            {activeJob
              ? `${progressPct}% complete • checkpoint ${activeJob.checkpoint_cursor ?? activeJob.processed} • every ${activeJob.checkpoint_every ?? 500}`
              : latestJob
                ? `Last job: ${latestJob.status} (${latestJob.processed}/${latestJob.total}) ${latestJob.finished_at ? `at ${latestJob.finished_at.slice(0, 19)}` : ''}`
                : 'No analyze jobs yet.'}
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>recent analyze jobs</h3>
        {analysisJobs.length === 0 ? (
          <div className="muted">No jobs yet.</div>
        ) : (
          <ul>
            {analysisJobs.slice(0, 8).map((j) => (
              <li key={j.id}>
                {j.id.slice(0, 8)} — {j.status} / {j.phase || 'n/a'} — {j.processed}/{j.total}
                {j.checkpoint_cursor != null ? ` • cp:${j.checkpoint_cursor}` : ''}
                {j.eta_sec != null ? ` • ETA ${j.eta_sec}s` : ''}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel" style={{ marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>alert scheduler</h3>
        {scheduler ? (
          <div style={{ display: 'grid', gap: 8 }}>
            <div>Status: {scheduler.enabled ? 'enabled' : 'disabled'} | interval: {scheduler.interval_sec}s | last run: {scheduler.last_run_at ? scheduler.last_run_at.slice(0, 19) : 'never'}</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={onToggleScheduler}>{scheduler.enabled ? 'Disable scheduler' : 'Enable scheduler'}</button>
              <button onClick={onSetSchedulerInterval}>Set interval</button>
            </div>
          </div>
        ) : <div className="muted">Scheduler state unavailable.</div>}
      </div>

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
              {r.name} — kind:{r.kind || '*'} severity:{r.severity || '*'} score≥{r.min_score} cooldown:{r.cooldown_min}m [{r.enabled ? 'enabled' : 'disabled'}]
              <span style={{ marginLeft: 8, display: 'inline-flex', gap: 6 }}>
                <button onClick={() => onToggleRule(r)}>{r.enabled ? 'Disable' : 'Enable'}</button>
                <button onClick={() => onEditRule(r)}>Edit</button>
                <button onClick={() => onDeleteRule(r)}>Delete</button>
              </span>
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
