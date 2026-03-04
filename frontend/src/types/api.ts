export type Overview = {
  files: number
  commits: number
  decisions: number
  modules: number
  risks: number
}

export type ChangeItem = { sha: string; message: string; date: string }
export type DecisionItem = {
  id: number
  title: string
  summary?: string
  status: string
  created_at: string
}
export type RiskItem = {
  area: string
  severity: 'low' | 'med' | 'high'
  kind: string
  rationale: string
  score: number
  created_at: string
}
export type ArchNode = { name: string }
export type ArchEdge = { from: string; to: string; type: string }
