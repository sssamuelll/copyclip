import type { ArchEdge, ArchNode, ChangeItem, DecisionItem, IssueItem, Overview, RiskItem, HeatmapItem } from '../types/api'

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`Request failed: ${r.status}`)
  return r.json() as Promise<T>
}

export const api = {
  overview: () => getJSON<Overview>('/api/overview'),
  changes: () => getJSON<{ items: ChangeItem[] }>('/api/changes'),
  decisions: () => getJSON<{ items: DecisionItem[] }>('/api/decisions'),
  risks: () => getJSON<{ items: RiskItem[] }>('/api/risks'),
  issues: () => getJSON<{ items: IssueItem[] }>('/api/issues'),
  heatmap: () => getJSON<{ items: HeatmapItem[] }>('/api/heatmap'),
  architecture: () => getJSON<{ nodes: ArchNode[]; edges: ArchEdge[] }>('/api/architecture/graph')
}
