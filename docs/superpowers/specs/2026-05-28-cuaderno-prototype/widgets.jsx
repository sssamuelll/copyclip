// widgets.jsx — Phase-2 widgets composed by the LLM into a frame.
// Each is a tiny presentational component. Exposed to window for cuaderno.jsx.

const WidgetHead = ({ kind, title, right }) => (
  <div className="widget-head">
    <span><span className="kind">{kind}</span> · {title}</span>
    {right ? <span>{right}</span> : null}
  </div>
);

// ─── sequence diagram (Example B Phase-2 glimpse) ────────────────────────────
function SequenceDiagram({ actors, steps }) {
  return (
    <div className="widget">
      <WidgetHead kind="widget" title="sequence" right={`${steps.length} calls`} />
      <div className="widget-body">
        <div className="seq">
          {actors.map((a, i) => (
            <div className="col" key={i}>
              <div className="who">{a}</div>
            </div>
          ))}
          {steps.map((s, i) => (
            <React.Fragment key={i}>
              {actors.map((_, ai) => {
                const isStart = ai === s.from;
                const inSpan = ai >= Math.min(s.from, s.to) && ai < Math.max(s.from, s.to);
                return (
                  <div className="lane" key={ai}>
                    {inSpan ? (
                      <>
                        <div className="step" style={{ left: '0%', width: '100%' }} />
                        {isStart && <span className="stepNote" style={{ left: '8px' }}>{s.label}</span>}
                      </>
                    ) : null}
                  </div>
                );
              })}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── callers tree (Example C Phase-2 glimpse) ────────────────────────────────
function CallersTree({ root, callers, openCite }) {
  return (
    <div className="widget">
      <WidgetHead kind="widget" title="callers" right={`${callers.length} sites`} />
      <div className="widget-body tree">
        <div className="node">
          <span className="glyph">◇</span>
          <span className="name">{root}</span>
        </div>
        {callers.map((c, i) => (
          <div className="node indent" key={i}>
            <span className="glyph">└─</span>
            <button className="cite" onClick={() => openCite(c.cite)}>
              <span className="arrow">▸</span>
              <span>{c.cite}</span>
            </button>
            <span style={{ color: 'var(--ink-3)', marginLeft: 4 }}>{c.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── graph subset (small visual) ─────────────────────────────────────────────
function GraphSubset() {
  const nodes = [
    { id: 'analyzer', label: 'analyzer.py', x: 40, y: 30, you: false },
    { id: 'db',       label: 'symbols (DB)', x: 200, y: 80, you: true  },
    { id: 'play',     label: 'playground.py', x: 360, y: 30, you: false },
    { id: 'map',      label: 'codebase_map', x: 200, y: 150, you: false },
  ];
  const edges = [
    { from: 'analyzer', to: 'db', label: 'writes' },
    { from: 'db', to: 'play', label: 'reads' },
    { from: 'db', to: 'map', label: 'reads' },
  ];
  const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
  return (
    <div className="widget">
      <WidgetHead kind="widget" title="graph subset" right="4 nodes · 3 edges" />
      <div className="widget-body">
        <div className="graph">
          {edges.map((e, i) => {
            const a = byId[e.from], b = byId[e.to];
            const dx = b.x - a.x, dy = b.y - a.y;
            const len = Math.sqrt(dx*dx + dy*dy);
            const ang = Math.atan2(dy, dx) * 180 / Math.PI;
            return (
              <div
                key={i}
                className="gedge"
                style={{ left: a.x + 50, top: a.y + 14, width: len, transform: `rotate(${ang}deg)` }}
              />
            );
          })}
          {nodes.map(n => (
            <div key={n.id} className={'gnode' + (n.you ? ' you' : '')} style={{ left: n.x, top: n.y }}>
              {n.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── executable code block (placeholder shell) ───────────────────────────────
function ExecutableBlock({ code, mocks, output }) {
  return (
    <div className="widget">
      <WidgetHead kind="executable" title="python · marimo block" right="run ▷" />
      <div className="widget-body" style={{ padding: 0 }}>
        <pre className="code" style={{ border: 0, borderRadius: 0 }}>
          {code.split('\n').map((l, i) => (
            <span className="ln" key={i}>{l || ' '}{'\n'}</span>
          ))}
        </pre>
        {mocks ? (
          <div style={{
            padding: '8px 18px',
            borderTop: '1px dashed var(--hairline)',
            fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-3)'
          }}>
            <span style={{ color: 'var(--accent)' }}>mocks · </span>{mocks}
          </div>
        ) : null}
        {output ? (
          <div style={{
            padding: '12px 18px', borderTop: '1px solid var(--hairline)',
            fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-2)',
            background: 'var(--paper)'
          }}>
            <div style={{ color: 'var(--ink-4)', fontSize: 10.5, letterSpacing: '.14em', textTransform: 'uppercase', marginBottom: 6 }}>output</div>
            <pre style={{ margin: 0, whiteSpace: 'pre' }}>{output}</pre>
          </div>
        ) : null}
      </div>
    </div>
  );
}

Object.assign(window, { SequenceDiagram, CallersTree, GraphSubset, ExecutableBlock });
