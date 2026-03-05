import type { ArchEdge, ArchNode, ChangeItem, DecisionHistoryItem, DecisionItem, IssueItem, Overview, RiskItem, HeatmapItem, FileItem, ContextPayload, ImpactResult, AgentResponse, AskResponse, RiskTrends, AlertRule, AlertsResponse, WeeklyExport, SchedulerState, AnalyzeJob, ArchaeologyResponse, StoryTimelineResponse, AdvisorCheckResponse, IdentityDriftResponse, DecisionLinkItem, CognitiveLoadResponse } from '../types/api'

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`Request failed: ${r.status}`)
  return r.json() as Promise<T>
}

async function postJSON<T>(url: string, data: any): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  if (!r.ok) throw new Error(`Request failed: ${r.status}`)
  return r.json() as Promise<T>
}

async function patchJSON<T>(url: string, data: any): Promise<T> {
  const r = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  if (!r.ok) throw new Error(`Request failed: ${r.status}`)
  return r.json() as Promise<T>
}

async function deleteJSON<T>(url: string): Promise<T> {
  const r = await fetch(url, { method: 'DELETE' })
  if (!r.ok) throw new Error(`Request failed: ${r.status}`)
  return r.json() as Promise<T>
}

export const api = {
  overview: () => getJSON<Overview>('/api/overview'),
  changes: () => getJSON<{ items: ChangeItem[] }>('/api/changes'),
  decisions: () => getJSON<{ items: DecisionItem[]; total?: number; limit?: number; offset?: number }>('/api/decisions'),
  decisionHistory: (id: number) => getJSON<{ items: DecisionHistoryItem[]; total?: number; limit?: number; offset?: number }>(`/api/decisions/${id}/history`),
  updateDecisionStatus: (id: number, status: string, note?: string) =>
    fetch(`/api/decisions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, note: note || '' })
    }).then(async (r) => {
      const data = await r.json()
      if (!r.ok) {
        const err = new Error(data?.message || data?.error || `Request failed: ${r.status}`)
        ;(err as any).payload = data
        throw err
      }
      return data
    }),
  addDecisionRef: (id: number, ref_type: 'file' | 'commit' | 'doc', ref_value: string) =>
    postJSON(`/api/decisions/${id}/refs`, { ref_type, ref_value }),
  decisionLinks: (id: number) => getJSON<{ items: DecisionLinkItem[] }>(`/api/decisions/${id}/links`),
  addDecisionLink: (id: number, link_type: 'file_glob' | 'module', target_pattern: string) =>
    postJSON(`/api/decisions/${id}/links`, { link_type, target_pattern }),
  risks: () => getJSON<{ items: RiskItem[]; total?: number; limit?: number; offset?: number }>('/api/risks'),
  riskTrends: () => getJSON<RiskTrends>('/api/risks/trends'),
  alerts: () => getJSON<AlertsResponse>('/api/alerts'),
  alertRules: () => getJSON<{ items: AlertRule[] }>('/api/alerts/rules'),
  schedulerState: () => getJSON<SchedulerState>('/api/alerts/scheduler'),
  setSchedulerState: (data: Partial<SchedulerState>) => postJSON<{ ok: boolean; scheduler: SchedulerState }>('/api/alerts/scheduler', data),
  startAnalyzeJob: () => postJSON<{ ok: boolean; job_id: string; already_running: boolean }>('/api/analyze/start', {}),
  resumeAnalyzeJob: () => postJSON<{ ok: boolean; job_id: string; already_running: boolean; resume_from?: number }>('/api/analyze/resume', {}),
  cancelAnalyzeJob: () => postJSON<{ ok: boolean; job_id: string; cancel_requested: boolean }>('/api/analyze/cancel', {}),
  analyzeStatus: () => getJSON<{ items: AnalyzeJob[] }>('/api/analyze/status'),
  upsertAlertRule: (rule: { name: string; kind?: string; severity?: string; min_score?: number; cooldown_min?: number; enabled?: boolean }) => postJSON<{ ok: boolean; name: string }>('/api/alerts/rules', rule),
  updateAlertRule: (id: number, patch: Partial<{ name: string; kind: string; severity: string; min_score: number; cooldown_min: number; enabled: boolean }>) =>
    patchJSON<{ ok: boolean; id: number }>(`/api/alerts/rules/${id}`, patch),
  deleteAlertRule: (id: number) => deleteJSON<{ ok: boolean; id: number }>(`/api/alerts/rules/${id}`),
  weeklyExport: (days = 7) => getJSON<WeeklyExport>(`/api/export/weekly?days=${days}`),
  issues: () => getJSON<{ items: IssueItem[] }>('/api/issues'),
  files: () => getJSON<{ items: FileItem[] }>('/api/files'),
  heatmap: () => getJSON<{ items: HeatmapItem[] }>('/api/heatmap'),
  impact: (path: string) => getJSON<ImpactResult>(`/api/impact?path=${encodeURIComponent(path)}`),
  archaeology: (file: string) => getJSON<ArchaeologyResponse>(`/api/archaeology?file=${encodeURIComponent(file)}`),
  storyTimeline: (range = '30d') => getJSON<StoryTimelineResponse>(`/api/story/timeline?range=${encodeURIComponent(range)}`),
  identityDrift: (range = '30d') => getJSON<IdentityDriftResponse>(`/api/identity/drift?range=${encodeURIComponent(range)}`),
  cognitiveLoad: () => getJSON<CognitiveLoadResponse>('/api/cognitive-load'),
  agentChat: (agent: string, message: string) => postJSON<AgentResponse>('/api/agents/chat', { agent, message }),
  getConfig: () => getJSON<Record<string, string>>('/api/config'),
  setConfig: (data: Record<string, string>) => postJSON<{ status: string }>('/api/config', data),
  architecture: () => getJSON<{ nodes: ArchNode[]; edges: ArchEdge[] }>('/api/architecture/graph'),
  ask: (question: string) => postJSON<AskResponse>('/api/ask', { question }),
  decisionAdvisorCheck: (intent: string, files: string[] = []) => postJSON<AdvisorCheckResponse>('/api/decision-advisor/check', { intent, files }),
  assembleContext: (p: ContextPayload) => postJSON<{ context: string; warnings: string[] }>('/api/assemble-context', p)
}
