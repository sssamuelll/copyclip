export function ContextBuilderPage() {
  return (
    <section className="page">
      <h2>Context Builder</h2>
      <p className="muted" style={{ marginBottom: '2rem' }}>
        Visually assemble your AI prompt. Select files, issues, and decisions to build the perfect context payload.
      </p>
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
        <div className="panel">
          <h3>Available Context</h3>
          <div className="muted" style={{ fontSize: '0.8rem', padding: '1rem' }}>
            [Context suggestions and RAG search will appear here]
          </div>
        </div>
        
        <div className="panel" style={{ border: '1px solid var(--accent)', background: 'rgba(255,255,255,0.02)' }}>
          <h3>Your Payload</h3>
          <div className="muted" style={{ fontSize: '0.8rem', padding: '1rem' }}>
            [Selected files will appear here]
          </div>
          <div style={{ padding: '1rem', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.8rem', opacity: 0.7 }}>0 Tokens estimated</span>
            <button className="btn primary">Copy Context</button>
          </div>
        </div>
      </div>
    </section>
  )
}
