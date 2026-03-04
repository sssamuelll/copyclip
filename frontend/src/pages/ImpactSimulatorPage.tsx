export function ImpactSimulatorPage() {
  return (
    <section className="page">
      <h2>Impact Simulator</h2>
      <p className="muted" style={{ marginBottom: '2rem' }}>
        Select a node or file to visualize its blast radius across the project.
      </p>
      
      <div className="panel" style={{ height: '500px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="muted">[Interactive dependency graph with blast-radius highlighting will go here]</div>
      </div>
    </section>
  )
}
