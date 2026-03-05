import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ChangeItem, CognitiveLoadItem, DecisionItem, IdentityDriftItem, Overview, RiskItem, StoryTimelineItem } from '../types/api'

type Props = {
  overview?: Overview
  changes: ChangeItem[]
  risks: RiskItem[]
  decisions: DecisionItem[]
}

export function AtlasPage({ overview, changes, risks, decisions }: Props) {
  const [storyItems, setStoryItems] = useState<StoryTimelineItem[]>([])
  const [driftCurrent, setDriftCurrent] = useState<IdentityDriftItem | null>(null)
  const [cognitiveItems, setCognitiveItems] = useState<CognitiveLoadItem[]>([])

  useEffect(() => {
    api.storyTimeline('30d').then((res) => setStoryItems(res.items || [])).catch(() => setStoryItems([]))
    api.identityDrift('30d').then((res) => setDriftCurrent(res.current || null)).catch(() => setDriftCurrent(null))
    api.cognitiveLoad().then((res) => setCognitiveItems(res.items || [])).catch(() => setCognitiveItems([]))
  }, [])

  const acceptedDecisions = decisions.filter(d => d.status === 'accepted' || d.status === 'resolved')
  const proposed = decisions.filter((d) => d.status === 'proposed').length
  
  // The "Soul" of the project is the story field in overview
  const projectStory = overview?.story || "Analyzing project soul... Run 'copyclip analyze' to generate the narrative narrative."

  return (
    <section className="atlas-container" style={{ display: 'grid', gap: 24, padding: '10px 0' }}>
      
      {/* 1. THE SOUL (NARRATIVE HERO) */}
      <div className="soul-hero-card" style={{ 
        background: 'linear-gradient(145deg, rgba(30,30,35,0.6) 0%, rgba(20,20,25,0.4) 100%)',
        border: '1px solid var(--border)',
        padding: 32,
        borderRadius: 8,
        position: 'relative',
        overflow: 'hidden'
      }}>
        <div style={{ position: 'absolute', top: 0, left: 0, width: 4, height: '100%', background: 'var(--accent-cyan)' }} />
        <div className="muted" style={{ fontSize: 11, marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1.5 }}>// the_soul_of_the_project</div>
        <h1 style={{ fontSize: 24, lineHeight: 1.4, fontWeight: 400, color: 'var(--text-primary)', maxWidth: '800px' }}>
          {projectStory}
        </h1>
        <div style={{ marginTop: 24, display: 'flex', gap: 16 }}>
           <div className="badge badge-low">active intent: {acceptedDecisions.length} rules</div>
           <div className="badge badge-med">alignment: {driftCurrent?.decision_alignment_score.toFixed(0) || 0}%</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 24 }}>
        
        {/* LEFT COLUMN: INTENT & EVOLUTION */}
        <div style={{ display: 'grid', gap: 24 }}>
          
          {/* 2. THE MANIFESTO (ACTIVE DECISIONS) */}
          <div className="section-panel" style={{ background: 'transparent', border: 'none', padding: 0 }}>
            <div className="section-header" style={{ marginBottom: 16 }}>
              <span className="section-title" style={{ fontSize: 14 }}>// active_intent_manifesto</span>
              <span className="muted" style={{ fontSize: 11 }}>the laws governing this codebase</span>
            </div>
            <div style={{ display: 'grid', gap: 12 }}>
              {acceptedDecisions.length ? acceptedDecisions.slice(0, 5).map(d => (
                <div key={d.id} style={{ 
                  padding: '16px 20px', 
                  background: 'rgba(255,255,255,0.03)', 
                  border: '1px solid rgba(255,255,255,0.05)',
                  borderRadius: 6,
                  display: 'grid',
                  gap: 4
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: 14, color: 'var(--accent-cyan)' }}>{d.title}</span>
                    <span className="muted" style={{ fontSize: 10 }}>#dec-{d.id}</span>
                  </div>
                  <div className="muted" style={{ fontSize: 12, lineHeight: 1.5 }}>{d.summary}</div>
                </div>
              )) : (
                <div className="muted" style={{ padding: 20, border: '1px dashed var(--border)', textAlign: 'center' }}>
                  No active architectural decisions. The intent is currently implicit.
                </div>
              )}
              {decisions.length > 5 && <div className="muted" style={{ fontSize: 11, textAlign: 'right' }}>+ {decisions.length - 5} more rules in decisions tab</div>}
            </div>
          </div>

          {/* 3. NARRATIVE DELTA (THE STORY SO FAR) */}
          <div className="section-panel">
            <div className="section-header">
              <span className="section-title">// intention_delta_timeline</span>
              <span className="muted" style={{ fontSize: 11 }}>how the logic is evolving</span>
            </div>
            <div style={{ maxHeight: '30vh', overflowY: 'auto', padding: '0 12px' }}>
              {storyItems.length ? storyItems.slice(0, 5).map((s, idx) => {
                const prev = storyItems[idx + 1]
                const currFocus = s.focus_areas?.[0]?.area || null
                const prevFocus = prev?.focus_areas?.[0]?.area || null
                let delta = "Stability maintained."
                if (currFocus && prevFocus && currFocus !== prevFocus) delta = `Focus shifted to ${currFocus}.`
                
                return (
                  <div key={s.id} className="row-item" style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', padding: '12px 0', flexDirection: 'column', alignItems: 'flex-start' }}>
                    <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>{s.generated_at.split('T')[0]}</div>
                    <div style={{ fontSize: 13 }}>{delta}</div>
                    <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{s.major_changes?.[0]?.message || "Refining existing logic."}</div>
                  </div>
                )
              }) : <div className="muted">No narrative snapshots.</div>}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: COGNITIVE DEBT & STATS */}
        <div style={{ display: 'grid', gap: 24 }}>
          
          {/* 4. FOG OF WAR (COGNITIVE DEBT) */}
          <div className="section-panel" style={{ height: 'fit-content' }}>
            <div className="section-header">
              <span className="section-title">// fog_of_war</span>
              <span className="muted" style={{ fontSize: 11 }}>understanding debt</span>
            </div>
            <div style={{ padding: 12, display: 'grid', gap: 10 }}>
              {cognitiveItems.length ? cognitiveItems.slice(0, 6).map((m) => (
                <div key={m.module} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12 }}>{m.module}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 60, height: 4, background: 'rgba(255,255,255,0.1)', borderRadius: 2 }}>
                      <div style={{ 
                        width: `${m.cognitive_debt_score}%`, 
                        height: '100%', 
                        background: m.fog_level === 'high' ? 'var(--accent-red)' : m.fog_level === 'med' ? 'var(--accent-amber)' : 'var(--accent-green)',
                        borderRadius: 2
                      }} />
                    </div>
                    <span className="muted" style={{ fontSize: 10, minWidth: 24 }}>{m.cognitive_debt_score.toFixed(0)}</span>
                  </div>
                </div>
              )) : <div className="muted">No data.</div>}
            </div>
          </div>

          {/* 5. VITAL SIGNS (THE NUMBERS) */}
          <div className="section-panel" style={{ height: 'fit-content' }}>
            <div className="section-header">
              <span className="section-title">// project_vitals</span>
            </div>
            <div style={{ padding: 12, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div className="panel" style={{ padding: 12, textAlign: 'center' }}>
                <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>files</div>
                <div style={{ fontSize: 18 }}>{overview?.files || 0}</div>
              </div>
              <div className="panel" style={{ padding: 12, textAlign: 'center' }}>
                <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>commits</div>
                <div style={{ fontSize: 18 }}>{overview?.commits || 0}</div>
              </div>
              <div className="panel" style={{ padding: 12, textAlign: 'center' }}>
                <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>risks</div>
                <div style={{ fontSize: 18, color: 'var(--accent-red)' }}>{overview?.risks || 0}</div>
              </div>
              <div className="panel" style={{ padding: 12, textAlign: 'center' }}>
                <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>proposals</div>
                <div style={{ fontSize: 18, color: 'var(--accent-amber)' }}>{proposed}</div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </section>
  )
}
