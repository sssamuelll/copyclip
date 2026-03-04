import type { ArchEdge, ArchNode, ChangeItem, DecisionHistoryItem, DecisionItem, IssueItem, Overview, RiskItem, HeatmapItem, FileItem, ContextPayload, ImpactResult, AgentResponse, AskResponse, RiskTrends } from '../types/api'

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
  risks: () => getJSON<{ items: RiskItem[]; total?: number; limit?: number; offset?: number }>('/api/risks'),
  riskTrends: () => getJSON<RiskTrends>('/api/risks/trends'),
  issues: () => getJSON<{ items: IssueItem[] }>('/api/issues'),
  files: () => getJSON<{ items: FileItem[] }>('/api/files'),
  heatmap: () => getJSON<{ items: HeatmapItem[] }>('/api/heatmap'),
  impact: (path: string) => getJSON<ImpactResult>(`/api/impact?path=${encodeURIComponent(path)}`),
  agentChat: (agent: string, message: string) => postJSON<AgentResponse>('/api/agents/chat', { agent, message }),
  architecture: () => getJSON<{ nodes: ArchNode[]; edges: ArchEdge[] }>('/api/architecture/graph'),
  ask: (question: string) => postJSON<AskResponse>('/api/ask', { question }),
  assembleContext: (p: ContextPayload) => postJSON<{ context: string; warnings: string[] }>('/api/assemble-context', p)
}
