export type Overview = {
  files: number
  commits: number
  decisions: number
  modules: number
  risks: number
  issues: number
  pulls?: number
  story: string
  meta?: {
    project?: string
    generated_at?: string
  }
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

export type AnalyzeJob = {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'canceled'
  phase?: string
  processed: number
  total: number
  message?: string
  checkpoint_cursor?: number
  checkpoint_every?: number
  started_at?: string
  finished_at?: string | null
  throughput_fps?: number | null
  eta_sec?: number | null
}

export type TreeNode = {
  name: string
  type: 'folder' | 'file'
  path: string
  children?: TreeNode[]
  lines?: number
  debt?: number
  symbol_count?: number
  file_count?: number
  avg_debt?: number
  language?: string
}

export type ArchNode = { name: string }
export type ArchEdge = { from: string; to: string; type: string }

export type ModuleSourceFile = {
  path: string
  content: string
  language: string
}

export type ModuleSourceResponse = {
  module: string
  files: ModuleSourceFile[]
  meta?: {
    project?: string
    generated_at?: string
  }
}

export type SymbolItem = {
  name: string
  kind: 'function' | 'class' | 'method' | 'interface' | 'trait' | 'enum' | 'struct'
  file_path: string
  line_start: number
  line_end: number
  methods?: string[]
  calls?: string[]
  called_by?: string[]
  inherits?: string[]
}

export type ModuleSymbolsResponse = {
  module: string
  symbols: SymbolItem[]
  meta?: {
    project?: string
    generated_at?: string
  }
}

export type ArchaeologyCommit = {
  sha: string
  author: string
  date: string
  message: string
}

export type ArchaeologyDecision = {
  id: number
  title: string
  status: string
  source_type?: string
  matched_refs: Array<{ ref_type: string; ref_value: string }>
}

export type ArchaeologyResponse = {
  file: string
  commits: ArchaeologyCommit[]
  related_decisions: ArchaeologyDecision[]
  meta?: {
    project?: string
    generated_at?: string
  }
}

export type StoryTimelineItem = {
  id: number
  generated_at: string
  focus_areas: Array<{ area: string; severity: string; kind: string; score: number }>
  major_changes: Array<{ sha: string; author: string; date: string; message: string }>
  open_questions: Array<{ decision_id: number; title: string; status: string }>
  summary: Record<string, number>
}

export type StoryTimelineResponse = {
  items: StoryTimelineItem[]
  total: number
  range_days: number
  meta?: {
    project?: string
    generated_at?: string
  }
}

export type AdvisorConflict = {
  decision_id: number
  title: string
  status: string
  why_conflict: string
  confidence: number
  suggested_alternative: string
  matched_refs?: Array<{ ref_type: string; ref_value: string }>
}

export type AdvisorCheckResponse = {
  ok: boolean
  conflicts: AdvisorConflict[]
  has_conflicts: boolean
  intent?: string
  checked_files?: string[]
  meta?: {
    project?: string
    generated_at?: string
  }
}

export type IdentityDriftItem = {
  id: number
  generated_at: string
  decision_alignment_score: number
  architecture_cohesion_delta: number
  risk_concentration_index: number
  causes: string[]
  summary: Record<string, any>
}

export type IdentityDriftResponse = {
  items: IdentityDriftItem[]
  total: number
  range_days: number
  current: IdentityDriftItem | null
  meta?: {
    project?: string
    generated_at?: string
  }
}

export type DecisionLinkItem = {
  id: number
  link_type: 'file_glob' | 'module'
  target_pattern: string
  created_at: string
}

export type CognitiveLoadItem = {
  module: string
  files: number
  churn: number
  avg_complexity: number
  decision_linked: boolean
  cognitive_debt_score: number
  fog_level: 'low' | 'med' | 'high'
}

export type CognitiveLoadResponse = {
  items: CognitiveLoadItem[]
  total: number
  last_review_at?: string | null
  meta?: {
    project?: string
    generated_at?: string
  }
}
