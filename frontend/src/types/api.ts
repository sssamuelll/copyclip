export type Overview = {
  files: number
  commits: number
  decisions: number
  modules: number
  risks: number
  issues: number
  story: string
}

export type FileItem = {
  path: string
  size: number
  language: string
}

export type ContextPayload = {
  files: string[]
  issues: string[]
  include_decisions: boolean
  minimize: 'basic' | 'aggressive' | 'structural'
}

export type ImpactResult = {
  target_module: string
  impacted_modules: string[]
}

export type HeatmapItem = {
  path: string
  size: number
  complexity: number
  churn: number
  score: number
}

export type ChangeItem = { sha: string; message: string; date: string }
export type DecisionItem = {
  id: number
  title: string
  summary?: string
  status: string
  source_type?: string
  created_at: string
}

export type DecisionHistoryItem = {
  id: number
  action: string
  from_status?: string | null
  to_status?: string | null
  note?: string | null
  created_at: string
}
export type IssueItem = {
  id: string
  title: string
  status: string
  labels: string[]
  author: string
  url: string
  source: string
  created_at: string
  updated_at: string
}
export type RiskItem = {
  area: string
  severity: 'low' | 'med' | 'high'
  kind: string
  rationale: string
  score: number
  created_at: string
}

export type RiskTrends = {
  latest: Record<string, number>
  previous: Record<string, number>
  delta: Record<string, number>
  has_previous: boolean
}
export type AgentResponse = {
  response: string
  agent: string
}

export type AskCitation = {
  type: 'decision' | 'risk' | 'commit'
  id: string | number
  label: string
}

export type AskResponse = {
  answer: string
  citations: AskCitation[]
  grounded: boolean
}

export type AlertRule = {
  id: number
  name: string
  kind?: string | null
  severity?: string | null
  min_score: number
  cooldown_min: number
  enabled: boolean
  last_triggered_at?: string | null
}

export type AlertEvent = {
  id: number
  rule_id?: number | null
  title: string
  detail?: string | null
  created_at: string
}

export type AlertsResponse = {
  fired: Array<{ rule: string; title: string; detail: string }>
  events: AlertEvent[]
  total: number
  limit: number
  offset: number
}

export type WeeklyExport = {
  markdown: string
  summary: Record<string, number>
}

export type SchedulerState = {
  enabled: boolean
  interval_sec: number
  last_run_at?: string | null
}

export type ArchNode = { name: string }
export type ArchEdge = { from: string; to: string; type: string }
