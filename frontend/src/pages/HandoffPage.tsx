import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { HandoffPacket, HandoffPacketListItem, HandoffPacketState, HandoffReviewSummary } from '../types/api'

type ComposerState = {
  taskPrompt: string
  declaredFiles: string
  declaredModules: string
  doNotTouch: string
  acceptanceCriteria: string
  delegationTarget: string
  approvedBy: string
}

const EMPTY_COMPOSER: ComposerState = {
  taskPrompt: '',
  declaredFiles: '',
  declaredModules: '',
  doNotTouch: '',
  acceptanceCriteria: '',
  delegationTarget: '',
  approvedBy: '',
}

const STATE_LABELS: Record<HandoffPacketState, string> = {
  draft: 'draft',
  ready_for_review: 'ready for review',
  approved_for_handoff: 'approved for handoff',
  delegated: 'delegated',
  change_received: 'change received',
  reviewed: 'reviewed',
  superseded: 'superseded',
  cancelled: 'cancelled',
}

function splitLines(value: string) {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

function serializeBoundaries(packet?: HandoffPacket | null) {
  if (!packet?.do_not_touch?.length) return ''
  return packet.do_not_touch.map((item) => `${item.target} | ${item.reason} | ${item.severity}`).join('\n')
}

function parseBoundaries(value: string) {
  return splitLines(value).map((line) => {
    const [target, reason, severity] = line.split('|').map((item) => item.trim())
    return {
      target,
      reason: reason || 'Explicit human boundary.',
      severity: severity || 'hard_boundary',
    }
  }).filter((item) => item.target)
}

function packetToComposer(packet: HandoffPacket): ComposerState {
  return {
    taskPrompt: packet.objective.summary,
    declaredFiles: packet.scope.declared_files.join('\n'),
    declaredModules: packet.scope.declared_modules.join('\n'),
    doNotTouch: serializeBoundaries(packet),
    acceptanceCriteria: packet.acceptance_criteria.map((item) => item.summary).join('\n'),
    delegationTarget: packet.meta.delegation_target || '',
    approvedBy: packet.meta.approved_by || '',
  }
}

export function HandoffPage({ onNotify }: { onNotify?: (msg: string) => void }) {
  const [composer, setComposer] = useState<ComposerState>(EMPTY_COMPOSER)
  const [queue, setQueue] = useState<HandoffPacketListItem[]>([])
  const [selectedPacket, setSelectedPacket] = useState<HandoffPacket | null>(null)
  const [selectedPacketId, setSelectedPacketId] = useState<string | null>(null)
  const [loadingQueue, setLoadingQueue] = useState(true)
  const [loadingPacket, setLoadingPacket] = useState(false)
  const [creating, setCreating] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [error, setError] = useState('')
  const [touchedFilesInput, setTouchedFilesInput] = useState('')
  const [reviewSummary, setReviewSummary] = useState<HandoffReviewSummary | null>(null)
  const [generatingReview, setGeneratingReview] = useState(false)
  const [reviewError, setReviewError] = useState('')

  const approvalReady = useMemo(() => composer.approvedBy.trim() && composer.delegationTarget.trim(), [composer.approvedBy, composer.delegationTarget])

  const loadQueue = async (preferredPacketId?: string | null) => {
    setLoadingQueue(true)
    try {
      const response = await api.handoffPackets()
      setQueue(response.items)
      const nextId = preferredPacketId || selectedPacketId || response.items[0]?.packet_id || null
      if (nextId) {
        setSelectedPacketId(nextId)
      } else {
        setSelectedPacket(null)
        setSelectedPacketId(null)
      }
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load handoff queue')
    } finally {
      setLoadingQueue(false)
    }
  }

  const loadPacket = async (packetId: string) => {
    setLoadingPacket(true)
    try {
      const response = await api.handoffPacket(packetId)
      setSelectedPacket(response.packet)
      setSelectedPacketId(packetId)
      setComposer((prev) => ({
        ...prev,
        delegationTarget: response.packet.meta.delegation_target || '',
        approvedBy: response.packet.meta.approved_by || '',
      }))
      setError('')
      setReviewError('')
      if (response.packet.meta.state === 'reviewed') {
        try {
          const reviewResp = await api.handoffReviewSummary(packetId)
          setReviewSummary(reviewResp.review_summary)
        } catch {
          setReviewSummary(null)
        }
      } else {
        setReviewSummary(null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load handoff packet')
    } finally {
      setLoadingPacket(false)
    }
  }

  const handleGenerateReview = async () => {
    if (!selectedPacketId || generatingReview) return
    const touchedFiles = splitLines(touchedFilesInput)
    if (!touchedFiles.length) {
      setReviewError('Enter at least one touched file to generate a review.')
      return
    }
    setGeneratingReview(true)
    setReviewError('')
    try {
      const response = await api.generateHandoffReviewSummary(selectedPacketId, { touched_files: touchedFiles })
      setReviewSummary(response.review_summary)
      setSelectedPacket(response.packet)
      await loadQueue(selectedPacketId)
      onNotify?.(`review ${response.review_summary.result.verdict}`)
    } catch (e) {
      setReviewError(e instanceof Error ? e.message : 'Failed to generate review summary')
    } finally {
      setGeneratingReview(false)
    }
  }

  useEffect(() => {
    loadQueue()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selectedPacketId) return
    loadPacket(selectedPacketId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPacketId])

  const updateComposer = (patch: Partial<ComposerState>) => setComposer((prev) => ({ ...prev, ...patch }))

  const handleCreate = async () => {
    if (!composer.taskPrompt.trim() || creating) return
    setCreating(true)
    try {
      const response = await api.createHandoffPacket({
        task_prompt: composer.taskPrompt.trim(),
        declared_files: splitLines(composer.declaredFiles),
        declared_modules: splitLines(composer.declaredModules),
        do_not_touch: parseBoundaries(composer.doNotTouch),
        acceptance_criteria: splitLines(composer.acceptanceCriteria),
        delegation_target: composer.delegationTarget.trim() || undefined,
      })
      const packetId = response.packet.meta.packet_id
      const packetState = response.packet.meta.state
      await loadQueue(packetId)
      onNotify?.(`handoff packet ${packetId} is ${STATE_LABELS[packetState]}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create handoff packet')
    } finally {
      setCreating(false)
    }
  }

  const handleStateTransition = async (state: HandoffPacketState) => {
    if (!selectedPacketId || updating) return
    setUpdating(true)
    try {
      const response = await api.updateHandoffPacket(selectedPacketId, {
        state,
        approved_by: composer.approvedBy.trim() || undefined,
        delegation_target: composer.delegationTarget.trim() || undefined,
      })
      setSelectedPacket(response.packet)
      await loadQueue(selectedPacketId)
      onNotify?.(`packet moved to ${STATE_LABELS[state]}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update handoff packet')
    } finally {
      setUpdating(false)
    }
  }

  const loadSelectedIntoComposer = () => {
    if (!selectedPacket) return
    setComposer(packetToComposer(selectedPacket))
    onNotify?.('packet loaded back into composer')
  }

  const stateActions = selectedPacket ? buildStateActions(selectedPacket.meta.state) : []

  return (
    <section style={{ display: 'grid', gap: 12 }}>
      <div className="page-header">
        <h2 className="page-title">handoff</h2>
      </div>

      <div className="section-panel">
        <div className="section-header">
          <span className="section-title">// safe_agent_handoff</span>
        </div>
        <div style={{ padding: 12, display: 'grid', gap: 12 }}>
          <div className="muted" style={{ maxWidth: 880 }}>
            Compose a bounded packet, inspect what the agent will and will not receive, then explicitly move it through pre-delegation review.
          </div>
          {error && <div className="error">{error}</div>}

          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'minmax(320px, 420px) minmax(0, 1fr)' }}>
            <div className="panel" style={{ padding: 12, display: 'grid', gap: 12 }}>
              <div className="section-title">// packet_composer</div>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className="muted">task prompt</span>
                <textarea value={composer.taskPrompt} onChange={(e) => updateComposer({ taskPrompt: e.target.value })} rows={5} placeholder="Build a bounded MCP handoff UI for review and delegation." />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className="muted">declared files · one per line</span>
                <textarea value={composer.declaredFiles} onChange={(e) => updateComposer({ declaredFiles: e.target.value })} rows={5} placeholder="frontend/src/pages/HandoffPage.tsx" />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className="muted">declared modules · one per line</span>
                <textarea value={composer.declaredModules} onChange={(e) => updateComposer({ declaredModules: e.target.value })} rows={3} placeholder="copyclip.intelligence" />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className="muted">do not touch · target | reason | severity</span>
                <textarea value={composer.doNotTouch} onChange={(e) => updateComposer({ doNotTouch: e.target.value })} rows={4} placeholder="frontend/src/pages/AskPage.tsx | keep ask surface unchanged | hard_boundary" />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span className="muted">acceptance criteria · one per line</span>
                <textarea value={composer.acceptanceCriteria} onChange={(e) => updateComposer({ acceptanceCriteria: e.target.value })} rows={4} placeholder="User can inspect the exact allowed write scope before delegation." />
              </label>
              <div style={{ display: 'grid', gap: 10, gridTemplateColumns: '1fr 1fr' }}>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className="muted">delegation target</span>
                  <input value={composer.delegationTarget} onChange={(e) => updateComposer({ delegationTarget: e.target.value })} placeholder="claude-code" />
                </label>
                <label style={{ display: 'grid', gap: 6 }}>
                  <span className="muted">approved by</span>
                  <input value={composer.approvedBy} onChange={(e) => updateComposer({ approvedBy: e.target.value })} placeholder="samuel" />
                </label>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button className="btn" onClick={handleCreate} disabled={!composer.taskPrompt.trim() || creating}>{creating ? 'creating…' : 'build packet'}</button>
                <button className="btn" onClick={() => setComposer(EMPTY_COMPOSER)} disabled={creating || updating}>reset</button>
                {selectedPacket && <button className="btn" onClick={loadSelectedIntoComposer}>edit selected in composer</button>}
              </div>
            </div>

            <div style={{ display: 'grid', gap: 12 }}>
              <div className="panel" style={{ padding: 12, display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div className="section-title">// packet_queue</div>
                  <span className="badge">{queue.length}</span>
                  <button className="btn" style={{ marginLeft: 'auto' }} onClick={() => loadQueue()} disabled={loadingQueue}>{loadingQueue ? 'refreshing…' : 'refresh'}</button>
                </div>
                {queue.length ? (
                  <div style={{ display: 'grid', gap: 8 }}>
                    {queue.map((item) => (
                      <button
                        key={item.packet_id}
                        className="row-item"
                        style={{
                          margin: 0,
                          border: selectedPacketId === item.packet_id ? '1px solid var(--accent-cyan)' : '1px solid var(--border)',
                          textAlign: 'left',
                          background: selectedPacketId === item.packet_id ? 'rgba(34,211,238,0.08)' : 'transparent',
                        }}
                        onClick={() => setSelectedPacketId(item.packet_id)}
                      >
                        <div style={{ display: 'grid', gap: 4, width: '100%' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                            <strong>{item.objective_summary || item.packet_id}</strong>
                            <span className={`badge badge-${stateTone(item.state)}`}>{STATE_LABELS[item.state]}</span>
                          </div>
                          <div className="muted" style={{ fontSize: 11 }}>{item.packet_id}</div>
                          <div className="muted" style={{ fontSize: 11 }}>updated {formatTimestamp(item.updated_at)}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="muted">No handoff packets yet. Build one from the composer.</div>
                )}
              </div>

              <div className="panel" style={{ padding: 12, display: 'grid', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <div className="section-title">// packet_review</div>
                  {selectedPacket && <span className={`badge badge-${stateTone(selectedPacket.meta.state)}`}>{STATE_LABELS[selectedPacket.meta.state]}</span>}
                  {selectedPacket?.meta.approved_by && <span className="badge">approved by {selectedPacket.meta.approved_by}</span>}
                  {loadingPacket && <span className="muted">loading…</span>}
                </div>

                {!selectedPacket ? (
                  <div className="muted">Select a packet to inspect its bounded handoff contract.</div>
                ) : (
                  <>
                    <div className="insight-card" style={{ margin: 0 }}>
                      <div className="insight-title">// objective</div>
                      <div className="insight-text">{selectedPacket.objective.summary}</div>
                      <div className="muted" style={{ marginTop: 8 }}>{selectedPacket.objective.intent}</div>
                      <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>success definition: {selectedPacket.objective.success_definition}</div>
                    </div>

                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {stateActions.map((action) => (
                        <button
                          key={action.state}
                          className="btn"
                          disabled={updating || (action.requiresApproval && !approvalReady)}
                          onClick={() => handleStateTransition(action.state)}
                        >
                          {updating ? 'updating…' : action.label}
                        </button>
                      ))}
                    </div>

                    <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
                      <ListCard title="// allowed_write_scope" items={selectedPacket.agent_consumable_packet.allowed_write_scope} empty="No allowed write scope declared yet." />
                      <ListCard title="// read_scope" items={selectedPacket.agent_consumable_packet.read_scope} empty="No supporting read scope selected." />
                      <ListCard title="// do_not_touch" items={selectedPacket.agent_consumable_packet.do_not_touch} empty="No explicit hard boundaries." />
                      <ListCard title="// acceptance_criteria" items={selectedPacket.agent_consumable_packet.acceptance_criteria} empty="No acceptance criteria yet." />
                    </div>

                    <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
                      <DetailCard title="// linked_decisions">
                        {selectedPacket.relevant_decisions.length ? selectedPacket.relevant_decisions.map((item) => (
                          <div key={item.id} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
                            <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center' }}>
                              <strong>{item.title}</strong>
                              <span className="badge" style={{ marginLeft: 'auto' }}>{item.status}</span>
                            </div>
                            <div className="muted" style={{ fontSize: 12 }}>{item.why_relevant}</div>
                            <div className="muted" style={{ fontSize: 11 }}>targets: {item.linked_targets.join(', ')}</div>
                          </div>
                        )) : <div className="muted">No decisions linked to this scope.</div>}
                      </DetailCard>

                      <DetailCard title="// dark_zones">
                        {selectedPacket.risk_dark_zones.length ? selectedPacket.risk_dark_zones.map((item) => (
                          <div key={String(item.risk_id)} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
                            <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center' }}>
                              <strong>{item.area}</strong>
                              <span className={`badge badge-${item.severity === 'high' ? 'high' : item.severity === 'medium' ? 'med' : 'low'}`} style={{ marginLeft: 'auto' }}>{item.kind}</span>
                            </div>
                            <div className="muted" style={{ fontSize: 12 }}>{item.why_it_matters}</div>
                            <div className="muted" style={{ fontSize: 11 }}>guardrail: {item.recommended_guardrail}</div>
                          </div>
                        )) : <div className="muted">No overlapping risk dark zones surfaced.</div>}
                      </DetailCard>
                    </div>

                    <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
                      <DetailCard title="// questions_to_clarify">
                        {selectedPacket.questions_to_clarify.length ? selectedPacket.questions_to_clarify.map((item, idx) => (
                          <div key={`${item.question}-${idx}`} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
                            <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center' }}>
                              <strong>{item.question}</strong>
                              <span className={`badge badge-${item.blocking ? 'high' : item.priority === 'medium' ? 'med' : 'low'}`} style={{ marginLeft: 'auto' }}>{item.blocking ? 'blocking' : item.priority}</span>
                            </div>
                            <div className="muted" style={{ fontSize: 11 }}>derived from: {item.derived_from.join(', ')}</div>
                          </div>
                        )) : <div className="muted">No unresolved clarification questions.</div>}
                      </DetailCard>

                      <DetailCard title="// agent_consumable_packet">
                        <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>This is the bounded slice the downstream agent should receive.</div>
                        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.5 }}>{JSON.stringify(selectedPacket.agent_consumable_packet, null, 2)}</pre>
                      </DetailCard>
                    </div>

                    {(selectedPacket.meta.state === 'change_received' || selectedPacket.meta.state === 'reviewed') && (
                      <div className="panel" style={{ padding: 12, display: 'grid', gap: 10, border: '1px solid var(--border)' }}>
                        <div className="section-title">// post_change_review</div>
                        <div className="muted" style={{ fontSize: 12 }}>
                          Paste the files the delegated agent touched. The review summary compares them against declared scope, decisions, risks, and boundaries.
                        </div>
                        {reviewError && <div className="error">{reviewError}</div>}
                        <label style={{ display: 'grid', gap: 6 }}>
                          <span className="muted">touched files · one per line</span>
                          <textarea
                            value={touchedFilesInput}
                            onChange={(e) => setTouchedFilesInput(e.target.value)}
                            rows={4}
                            placeholder="src/copyclip/intelligence/server.py"
                          />
                        </label>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          <button
                            className="btn"
                            onClick={handleGenerateReview}
                            disabled={generatingReview || !touchedFilesInput.trim()}
                          >
                            {generatingReview ? 'generating…' : reviewSummary ? 're-generate review' : 'generate review'}
                          </button>
                        </div>

                        {reviewSummary && (
                          <ReviewSummaryView summary={reviewSummary} />
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

type StateAction = {
  label: string
  state: HandoffPacketState
  requiresApproval?: boolean
}

function buildStateActions(state: HandoffPacketState): StateAction[] {
  switch (state) {
    case 'draft':
      return [{ label: 'mark ready for review', state: 'ready_for_review' as const }]
    case 'ready_for_review':
      return [
        { label: 'send back to draft', state: 'draft' as const },
        { label: 'approve for handoff', state: 'approved_for_handoff' as const, requiresApproval: true },
      ]
    case 'approved_for_handoff':
      return [
        { label: 'mark delegated', state: 'delegated' as const },
        { label: 'cancel', state: 'cancelled' as const },
      ]
    case 'delegated':
      return [
        { label: 'mark change received', state: 'change_received' as const },
        { label: 'cancel', state: 'cancelled' as const },
      ]
    case 'change_received':
    case 'reviewed':
    default:
      return []
  }
}

function stateTone(state: HandoffPacketState) {
  if (state === 'approved_for_handoff' || state === 'reviewed') return 'high'
  if (state === 'ready_for_review' || state === 'change_received') return 'med'
  return 'low'
}

function formatTimestamp(value?: string | null) {
  if (!value) return 'n/a'
  return value.replace('T', ' ').replace('Z', ' UTC')
}

function DetailCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="insight-card" style={{ margin: 0 }}>
      <div className="insight-title">{title}</div>
      <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>{children}</div>
    </div>
  )
}

function ListCard({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <DetailCard title={title}>
      {items.length ? (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {items.map((item) => <li key={item} className="muted">{item}</li>)}
        </ul>
      ) : (
        <div className="muted">{empty}</div>
      )}
    </DetailCard>
  )
}

function verdictTone(verdict: string) {
  if (verdict === 'accepted') return 'high'
  if (verdict === 'changes_requested') return 'low'
  return 'med'
}

function severityTone(severity: string) {
  if (severity === 'high' || severity === 'hard_boundary') return 'high'
  if (severity === 'medium') return 'med'
  return 'low'
}

function ReviewSummaryView({ summary }: { summary: HandoffReviewSummary }) {
  const { result, scope_check, decision_conflicts, blast_radius, dark_zone_entry, unresolved_questions } = summary
  const boundaryViolations = scope_check.boundary_violations || []
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div className="insight-card" style={{ margin: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div className="insight-title">// verdict</div>
          <span className={`badge badge-${verdictTone(result.verdict)}`}>{result.verdict}</span>
          <span className="badge" style={{ marginLeft: 'auto' }}>confidence: {result.confidence}</span>
        </div>
        <div className="insight-text" style={{ marginTop: 8 }}>{result.summary}</div>
      </div>

      <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
        <DetailCard title="// scope_check">
          <div className="muted" style={{ fontSize: 12 }}>{scope_check.summary}</div>
          {scope_check.out_of_scope_touches.length ? (
            <div>
              <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>out of declared scope:</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {scope_check.out_of_scope_touches.map((f) => <li key={f} className="muted">{f}</li>)}
              </ul>
            </div>
          ) : <div className="muted" style={{ fontSize: 11 }}>all touches stayed in declared scope.</div>}
          {boundaryViolations.length > 0 && (
            <div>
              <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>boundary violations:</div>
              {boundaryViolations.map((v, idx) => (
                <div key={`${v.target}-${idx}`} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
                  <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center' }}>
                    <strong>{v.touched_file}</strong>
                    <span className={`badge badge-${severityTone(v.severity)}`} style={{ marginLeft: 'auto' }}>{v.severity}</span>
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>boundary: {v.target}</div>
                  <div className="muted" style={{ fontSize: 11 }}>{v.reason}</div>
                </div>
              ))}
            </div>
          )}
        </DetailCard>

        <DetailCard title="// decision_conflicts">
          {decision_conflicts.length ? decision_conflicts.map((c) => (
            <div key={c.decision_id} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center' }}>
                <strong>#{c.decision_id} {c.title}</strong>
                <span className={`badge badge-${severityTone(c.severity)}`} style={{ marginLeft: 'auto' }}>{c.severity}</span>
              </div>
              <div className="muted" style={{ fontSize: 12 }}>{c.summary}</div>
              <div className="muted" style={{ fontSize: 11 }}>touched: {c.touched_targets.join(', ')}</div>
            </div>
          )) : <div className="muted">No decision conflicts surfaced.</div>}
        </DetailCard>

        <DetailCard title="// blast_radius">
          <div className="muted" style={{ fontSize: 12 }}>{blast_radius.impact_summary}</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
            <span className="badge">size: {blast_radius.estimated_size}</span>
            <span className="badge">files: {blast_radius.touched_file_count}</span>
          </div>
          {blast_radius.impacted_modules.length ? (
            <ul style={{ margin: 0, paddingLeft: 18, marginTop: 8 }}>
              {blast_radius.impacted_modules.map((m) => <li key={m} className="muted">{m}</li>)}
            </ul>
          ) : <div className="muted" style={{ fontSize: 11 }}>No module signal for touched files.</div>}
        </DetailCard>

        <DetailCard title="// dark_zone_entry">
          {dark_zone_entry.length ? dark_zone_entry.map((d) => (
            <div key={d.area} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center' }}>
                <strong>{d.area}</strong>
                <span className={`badge badge-${d.expected ? 'med' : 'high'}`} style={{ marginLeft: 'auto' }}>{d.expected ? 'acknowledged' : 'unexpected'}</span>
              </div>
              <div className="muted" style={{ fontSize: 12 }}>{d.reason}</div>
            </div>
          )) : <div className="muted">No dark zone entries detected.</div>}
        </DetailCard>

        <DetailCard title="// unresolved_questions">
          {unresolved_questions.length ? unresolved_questions.map((q, idx) => (
            <div key={`${q.question}-${idx}`} className="row-item" style={{ margin: 0, border: '1px solid var(--border)', flexDirection: 'column', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', width: '100%', gap: 8, alignItems: 'center' }}>
                <strong>{q.question}</strong>
                <span className={`badge badge-${q.blocking ? 'high' : q.priority === 'medium' ? 'med' : 'low'}`} style={{ marginLeft: 'auto' }}>{q.blocking ? 'blocking' : q.priority}</span>
              </div>
              {q.derived_from?.length ? <div className="muted" style={{ fontSize: 11 }}>derived from: {q.derived_from.join(', ')}</div> : null}
            </div>
          )) : <div className="muted">No unresolved questions remain.</div>}
        </DetailCard>
      </div>
    </div>
  )
}
