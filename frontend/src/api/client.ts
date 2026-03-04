import type { ArchEdge, ArchNode, ChangeItem, DecisionHistoryItem, DecisionItem, IssueItem, Overview, RiskItem, HeatmapItem, FileItem, ContextPayload, ImpactResult, AgentResponse, AskResponse, RiskTrends, AlertRule, AlertsResponse, WeeklyExport } from '../types/api'

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
  risks: () => getJSON<{ items: RiskItem[]; total?: number; limit?: number; offset?: number }>('/api/risks'),
  riskTrends: () => getJSON<RiskTrends>('/api/risks/trends'),
  alerts: () => getJSON<AlertsResponse>('/api/alerts'),
  alertRules: () => getJSON<{ items: AlertRule[] }>('/api/alerts/rules'),
  upsertAlertRule: (rule: { name: string; kind?: string; severity?: string; min_score?: number; cooldown_min?: number; enabled?: boolean }) => postJSON<{ ok: boolean; name: string }>('/api/alerts/rules', rule),
  weeklyExport: (days = 7) => getJSON<WeeklyExport>(`/api/export/weekly?days=${days}`),
  issues: () => getJSON<{ items: IssueItem[] }>('/api/issues'),
  files: () => getJSON<{ items: FileItem[] }>('/api/files'),
  heatmap: () => getJSON<{ items: HeatmapItem[] }>('/api/heatmap'),
  impact: (path: string) => getJSON<ImpactResult>(`/api/impact?path=${encodeURIComponent(path)}`),
  agentChat: (agent: string, message: string) => postJSON<AgentResponse>('/api/agents/chat', { agent, message }),
  getConfig: () => getJSON<Record<string, string>>('/api/config'),
  setConfig: (data: Record<string, string>) => postJSON<{ status: string }>('/api/config', data),
  architecture: () => getJSON<{ nodes: ArchNode[]; edges: ArchEdge[] }>('/api/architecture/graph'),
  ask: (question: string) => postJSON<AskResponse>('/api/ask', { question }),
  assembleContext: (p: ContextPayload) => postJSON<{ context: string; warnings: string[] }>('/api/assemble-context', p)
}
