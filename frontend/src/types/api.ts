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
  type: 'decision' | 'risk' | 'commit' | 'file'
  id: string | number
  label: string
}

export type AskEvidenceItem = {
  evidence_id: string
  id: string | number
  label: string
  snippet?: string
  score: number
  why_selected: string[]
  ref: {
    type: 'file' | 'commit' | 'decision' | 'risk' | 'symbol'
    target: string | number
  }
  related_file?: string
}

export type AskEvidenceGroup = {
  files: AskEvidenceItem[]
  commits: AskEvidenceItem[]
  decisions: AskEvidenceItem[]
  risks: AskEvidenceItem[]
  symbols: AskEvidenceItem[]
}

export type AskResponse = {
  answer: string
  answer_summary: string
  answer_kind: 'grounded_answer' | 'insufficient_evidence' | 'contradiction_detected'
  confidence: 'low' | 'medium' | 'high'
  citations: AskCitation[]
  grounded: boolean
  evidence: AskEvidenceGroup
  answer_evidence_ids: string[]
  evidence_selection_rationale: string[]
  gaps_or_unknowns: string[]
  next_questions: string[]
  next_drill_down: {
    type: 'file' | 'commit' | 'decision' | 'risk' | 'module' | 'none'
    target: string | number | null
  }
  bundle_manifest?: Array<Record<string, unknown>>
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

export type ReacquaintanceEvidenceItem = {
  id: string
  type: 'story' | 'snapshot' | 'file' | 'commit' | 'decision' | 'risk'
  label: string
  ref: string
}

export type ReacquaintanceProjectRefresher = {
  summary: string
  confidence: 'low' | 'medium' | 'high'
  why_now: string
  evidence: string[]
}

export type ReacquaintanceTopChange = {
  title: string
  importance: number
  summary: string
  change_kind: string
  primary_area: string
  evidence: string[]
  why_selected: string[]
}

export type ReacquaintanceReadFirstItem = {
  rank: number
  target_type: 'file' | 'module' | 'decision'
  target: string
  score: number
  reason: string
  expected_payoff: string
  estimated_minutes: number
  evidence: string[]
}

export type ReacquaintanceDecisionItem = {
  id: number
  title: string
  status: string
  relevance_score: number
  why_now: string
  evidence: string[]
}

export type ReacquaintanceRiskItem = {
  area: string
  severity: string
  kind: string
  score: number
  summary: string
  recommended_first_action: string
  evidence: string[]
} | null

export type ReacquaintanceQuestion = {
  question: string
  priority: 'low' | 'medium' | 'high'
  derived_from: string[]
  next_step: string
}

export type ReacquaintanceResponse = {
  meta: {
    project?: string
    generated_at?: string
    briefing_version?: string
    baseline_mode?: string
    baseline_label?: string
    baseline_started_at?: string | null
    baseline_available?: boolean
    confidence?: 'low' | 'medium' | 'high'
  }
  project_refresher: ReacquaintanceProjectRefresher
  top_changes: ReacquaintanceTopChange[]
  read_first: ReacquaintanceReadFirstItem[]
  relevant_decisions: ReacquaintanceDecisionItem[]
  top_risk: ReacquaintanceRiskItem
  open_questions: ReacquaintanceQuestion[]
  evidence_index: ReacquaintanceEvidenceItem[]
  fallback_notes: string[]
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

export type HandoffPacketState =
  | 'draft'
  | 'ready_for_review'
  | 'approved_for_handoff'
  | 'delegated'
  | 'change_received'
  | 'reviewed'
  | 'superseded'
  | 'cancelled'

export type HandoffReviewState = 'not_started' | 'generated' | 'human_reviewed' | 'accepted' | 'changes_requested'

export type HandoffBoundary = {
  target: string
  reason: string
  severity: string
  source?: string[]
}

export type HandoffDecision = {
  id: number
  title: string
  status: string
  why_relevant: string
  linked_targets: string[]
  evidence: string[]
}

export type HandoffRiskDarkZone = {
  risk_id: string | number
  area: string
  kind: string
  severity: string
  score: number
  why_it_matters: string
  recommended_guardrail: string
  evidence: string[]
}

export type HandoffQuestion = {
  question: string
  priority: string
  blocking: boolean
  derived_from: string[]
  resolution?: string | null
}

export type HandoffAcceptanceCriterion = {
  id: string
  summary: string
  check_type: string
}

export type HandoffEvidenceItem = {
  id: string
  type: string
  label: string
  ref: string | number
}

export type HandoffBundleManifestItem = {
  kind?: string
  path?: string
  score?: number
  reasons?: string[]
}

export type HandoffPacket = {
  meta: {
    packet_id: string
    packet_version: string
    state: HandoffPacketState
    created_at: string
    updated_at: string
    project: string
    created_by: string
    approved_by?: string | null
    delegation_target?: string | null
    source_task?: { kind: string; value: string }
  }
  objective: {
    summary: string
    task_type: string
    intent: string
    success_definition: string
  }
  scope: {
    declared_files: string[]
    declared_modules: string[]
    supporting_files: string[]
    supporting_context_rationale: string[]
    out_of_scope_modules: string[]
    scope_rationale: string[]
  }
  constraints: Array<{
    constraint_id: string
    type: string
    summary: string
    source: string[]
    severity: string
    origin: string
  }>
  do_not_touch: HandoffBoundary[]
  relevant_decisions: HandoffDecision[]
  risk_dark_zones: HandoffRiskDarkZone[]
  questions_to_clarify: HandoffQuestion[]
  acceptance_criteria: HandoffAcceptanceCriterion[]
  agent_consumable_packet: {
    objective: string
    allowed_write_scope: string[]
    read_scope: string[]
    constraints: string[]
    do_not_touch: string[]
    questions_to_clarify: string[]
    acceptance_criteria: string[]
  }
  review_contract: {
    expected_review_type: string
    compare_scope_against_touched_files: boolean
    check_decision_conflicts: boolean
    check_dark_zone_entry: boolean
    check_blast_radius: boolean
    required_human_questions: string[]
  }
  evidence_index: HandoffEvidenceItem[]
  notes: string[]
  bundle_manifest: HandoffBundleManifestItem[]
}

export type HandoffPacketListItem = {
  packet_id: string
  state: HandoffPacketState
  objective_summary: string
  created_at: string
  updated_at: string
}

export type HandoffPacketListResponse = {
  items: HandoffPacketListItem[]
  total: number
  limit: number
  offset: number
  meta?: {
    project?: string
    generated_at?: string
  }
}

export type HandoffReviewScopeCheck = {
  declared_scope: string[]
  touched_files: string[]
  out_of_scope_touches: string[]
  boundary_violations: Array<{
    target: string
    touched_file: string
    reason: string
    severity: string
  }>
  summary: string
}

export type HandoffReviewDecisionConflict = {
  decision_id: number
  title: string
  status: string
  severity: 'high' | 'medium' | 'low' | string
  summary: string
  touched_targets: string[]
  evidence: string[]
}

export type HandoffReviewBlastRadius = {
  impacted_modules: string[]
  touched_file_count: number
  estimated_size: 'small' | 'medium' | 'large' | string
  impact_summary: string
}

export type HandoffReviewDarkZoneEntry = {
  area: string
  expected: boolean
  reason: string
  evidence: string[]
}

export type HandoffReviewUnresolvedQuestion = {
  question: string
  priority: 'low' | 'medium' | 'high' | string
  blocking: boolean
  derived_from: string[]
}

export type HandoffReviewResult = {
  summary: string
  verdict: 'accepted' | 'changes_requested' | 'needs_human_review' | string
  confidence: 'low' | 'medium' | 'high' | string
}

export type HandoffReviewSummary = {
  meta: {
    review_id: string
    packet_id: string
    review_state: HandoffReviewState
    generated_at: string
  }
  result: HandoffReviewResult
  scope_check: HandoffReviewScopeCheck
  decision_conflicts: HandoffReviewDecisionConflict[]
  blast_radius: HandoffReviewBlastRadius
  dark_zone_entry: HandoffReviewDarkZoneEntry[]
  unresolved_questions: HandoffReviewUnresolvedQuestion[]
  review_evidence: HandoffEvidenceItem[]
}
