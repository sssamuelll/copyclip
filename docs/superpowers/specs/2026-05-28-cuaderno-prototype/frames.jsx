// frames.jsx — content of each scene's frame. Each is a component receiving
// { openCite, ask } so citations open the side panel and follow-ups can be
// clicked to trigger the next question.

const Cite = ({ path, onClick }) => (
  <button className="cite cite-block" onClick={() => onClick(path)}>
    <span className="arrow">▸</span>
    <span>{path}</span>
  </button>
);

const CiteInline = ({ path, onClick }) => (
  <button className="cite" onClick={() => onClick(path)}>
    <span className="arrow">▸</span>
    <span>{path}</span>
  </button>
);

const CiteStack = ({ items, onClick }) => (
  <div className="cite-stack">
    {items.map((it, i) => (
      <a key={i} onClick={() => onClick(it.path)}>
        <span className="arrow">▸</span>
        <span>{it.path}</span>
        {it.note ? <span style={{ color: 'var(--ink-3)' }}>  {it.note}</span> : null}
      </a>
    ))}
  </div>
);

// ─── Empty / first-time ──────────────────────────────────────────────────────
function FrameEmpty({ ask }) {
  return (
    <div className="empty">
      <h1 className="hi">First time in this project. <em>What interests you?</em></h1>
      <p className="sub">
        Ask anything in your own words — broad ("what does this project do?"),
        relational ("how do X and Y connect?"), or atomic ("why is line 152 written this way?").
        Every answer is anchored to real code; nothing invented.
      </p>
      <div className="starters">
        <div className="cap">or start from here</div>
        <button className="starter" onClick={() => ask('what does this project do?')}>
          <span className="glyph">A</span>
          <span>what does this project do?</span>
          <span className="arr">→</span>
        </button>
        <button className="starter" onClick={() => ask('how do the analyzer and the playground connect?')}>
          <span className="glyph">B</span>
          <span>how do the analyzer and the playground connect?</span>
          <span className="arr">→</span>
        </button>
        <button className="starter" onClick={() => ask('why does _module_from_relpath use slash instead of dot?')}>
          <span className="glyph">C</span>
          <span>why does <code style={{ fontFamily: 'var(--font-mono)', fontStyle: 'normal', fontSize: '0.85em' }}>_module_from_relpath</code> use slash instead of dot?</span>
          <span className="arr">→</span>
        </button>
      </div>
    </div>
  );
}

// ─── Mid-stream (tool calls running, text starting to stream) ────────────────
function FrameMidStream({ tools, partial }) {
  return (
    <>
      <div className="cua-question">
        <span className="label">you asked</span>
        <span className="q">how do the analyzer and the playground connect?</span>
      </div>
      <div className="toolcalls" aria-label="LLM tool calls">
        {tools.map((t, i) => (
          <div key={i} className={`row ${t.state}`}>
            <span className="tag">
              {t.state === 'done' ? '✓' : t.state === 'running' ? '◐' : '·'}
            </span>
            <span className="name">{t.name}</span>
            <span className="args">{t.args}</span>
            <span className="meta">
              {t.state === 'done' ? `${t.ms} ms` : t.state === 'running' ? 'running…' : 'queued'}
            </span>
          </div>
        ))}
      </div>
      <p className="cua-lead">
        {partial}
        <span className="streaming-caret" />
      </p>
    </>
  );
}

// ─── Example A — broad ───────────────────────────────────────────────────────
function FrameA({ openCite, ask }) {
  return (
    <>
      <div className="cua-question">
        <span className="label">you asked</span>
        <span className="q">what does this project do?</span>
      </div>
      <p className="cua-lead">
        CopyClip is a personal tool for understanding code <em>the AI wrote for you</em>.
        Three subsystems compose its core.
      </p>
      <ol className="cua-list">
        <li>
          <div>
            <div className="head">Analyzer</div>
            <div className="desc">Parses the repo, extracts symbols, builds the architecture graph.</div>
            <Cite path="src/copyclip/intelligence/analyzer.py:1-50" onClick={openCite} />
          </div>
        </li>
        <li>
          <div>
            <div className="head">Codebase Map</div>
            <div className="desc">Frontend that renders the graph as an interactive, navigable 3D atlas.</div>
            <Cite path="frontend/src/pages/Atlas3DPage.tsx:1-60" onClick={openCite} />
          </div>
        </li>
        <li>
          <div>
            <div className="head">Cuaderno (this surface)</div>
            <div className="desc">
              LLM-tutor surface that explains the code at whatever level the question
              demands — anchored in citations, never inventing.
            </div>
            <Cite path="src/copyclip/intelligence/playground.py:1-30" onClick={openCite} />
          </div>
        </li>
      </ol>
      <div className="callout">
        <div className="kicker">explicit commitment · 2026-05-26</div>
        <p>
          Not a commercial product. Discipline-as-artifact — preserve rigor, drop
          publication aspirations.
        </p>
        <div style={{ marginTop: 8 }}>
          <CiteInline path="docs/REJECTED.md" onClick={openCite} />
        </div>
      </div>
      <GraphSubset />
      <div className="followups">
        <div className="cap">go deeper</div>
        <div className="btns">
          <button className="fu" onClick={() => ask('explore the analyzer')}><span className="arr">↳</span> the analyzer</button>
          <button className="fu" onClick={() => ask('how do the analyzer and the playground connect?')}><span className="arr">↳</span> the cuaderno</button>
          <button className="fu" onClick={() => ask('walk me through the codebase map')}><span className="arr">↳</span> the codebase map</button>
        </div>
      </div>
    </>
  );
}

// ─── Example B — intermediate (ASCII diagram + sequence widget) ──────────────
function FrameB({ openCite, ask }) {
  const ascii =
`  ANALYZER ──writes──▶  ┌──────────┐  ◀──reads── PLAYGROUND
                        │  symbols │
                        │   (DB)   │
                        └──────────┘
     │                                            │
     │ INSERT INTO symbols                        │ SELECT … WHERE
     │ (name, kind, file_path,                    │ file_path=? AND name=?
     │  line_start, module)                       │ AND kind IN (…)`;
  return (
    <>
      <div className="cua-question">
        <span className="label">you asked</span>
        <span className="q">how do the analyzer and the playground connect?</span>
      </div>
      <p className="cua-lead">
        The playground <em>reads</em> data the analyzer <em>wrote</em>. The seam is
        the <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.92em' }}>symbols</code> table in SQLite.
      </p>
      <pre className="ascii">{ascii}</pre>
      <p className="cua-p">
        The analyzer populates the table from <span className="cua-strong">analyze(root)</span>:
      </p>
      <Cite path="src/copyclip/intelligence/analyzer.py:646-680" onClick={openCite} />
      <p className="cua-p" style={{ marginTop: 14 }}>
        The playground reads it to resolve a function reference before executing:
      </p>
      <Cite path="src/copyclip/intelligence/playground.py:266-292" onClick={openCite} />
      <div className="callout">
        <div className="kicker">key point</div>
        <p>
          The playground derives the Python module from the file path,
          <em> not</em> from the DB's <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.92em' }}>module</code> column.
          That was fixed in <span className="cua-strong">a0dae63</span> because the column is
          slash-style (<code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.92em' }}>copyclip/intelligence</code>) and
          Python needs dotted.
        </p>
        <CiteStack
          items={[
            { path: 'src/copyclip/intelligence/playground.py:303-314', note: '— the divergence' },
            { path: 'commit a0dae63', note: '— the fix' },
          ]}
          onClick={openCite}
        />
      </div>
      <SequenceDiagram
        actors={['analyze(root)', 'symbols (DB)', 'resolve_ref()']}
        steps={[
          { from: 0, to: 1, label: 'INSERT' },
          { from: 1, to: 2, label: 'SELECT' },
          { from: 2, to: 1, label: '· verify' },
        ]}
      />
      <div className="followups">
        <div className="cap">go deeper</div>
        <div className="btns">
          <button className="fu" onClick={() => ask('why does _module_from_relpath use slash instead of dot?')}><span className="arr">↳</span> why slash, not dot?</button>
          <button className="fu" onClick={() => ask('show me the commit that introduced the fix')}><span className="arr">↳</span> the commit a0dae63</button>
          <button className="fu" onClick={() => ask('run this flow with a fake symbol')}><span className="arr">↳</span> run it with a fake symbol</button>
        </div>
      </div>
    </>
  );
}

// ─── Example C — atomic (line-level + code + blame) ──────────────────────────
function FrameC({ openCite, ask }) {
  const code =
`def _module_from_relpath(rel: str) -> str:
    parts = [p for p in rel.split("/") if p]
    if len(parts) <= 1:
        return "root"
    if parts[0] in {"src", "lib"} and len(parts) > 2:
        parts = parts[1:]
    if len(parts) == 2:
        return parts[0] if parts[0] in {"api", "utils"} else parts[1]
    return "/".join(parts[:-1])   # ← returns "copyclip/intelligence"`;
  return (
    <>
      <div className="cua-question">
        <span className="label">you asked</span>
        <span className="q">why does _module_from_relpath use slash instead of dot?</span>
      </div>
      <p className="cua-lead">
        Because its primary consumer is <em>not</em> Python imports — it's the
        architecture graph and cross-language queries.
      </p>
      <p className="cua-p">The body:</p>
      <Cite path="src/copyclip/intelligence/analyzer.py:152-164" onClick={openCite} />
      <pre className="code" style={{ marginTop: 10 }}>
        {code.split('\n').map((l, i) => (
          <span className="ln" key={i}>{l || ' '}{'\n'}</span>
        ))}
      </pre>
      <p className="cua-p" style={{ marginTop: 18 }}>
        Both call sites consume the result as a <span className="cua-strong">path-string</span>
        {' '}for joins, comparisons, and matching against the architecture graph. Neither uses it
        as a direct <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.92em' }}>from {'{mod}'} import</code>.
      </p>
      <CallersTree
        root="_module_from_relpath"
        openCite={openCite}
        callers={[
          { cite: 'analyzer.py:486', note: 'changes detected by module' },
          { cite: 'analyzer.py:660', note: 'INSERT INTO symbols(module=…)' },
        ]}
      />
      <p className="cua-p">
        The playground <em>does</em> need dotted Python, so it derives its own version
        (<code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.92em' }}>_module_from_file</code>)
        instead of trusting this value:
      </p>
      <Cite path="src/copyclip/intelligence/playground.py:501-509" onClick={openCite} />
      <div className="callout">
        <div className="kicker">recovered decision</div>
        <p>
          The <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.92em' }}>symbols.module</code> field is
          multi-language by design. Python is just one of the consumers; slash format is the shared format.
        </p>
      </div>
      <div className="followups">
        <div className="cap">go deeper</div>
        <div className="btns">
          <button className="fu" onClick={() => ask('show me the commit that introduced this separation')}><span className="arr">↳</span> the commit that split the formats</button>
          <button className="fu" onClick={() => ask('what other languages does the analyzer index?')}><span className="arr">↳</span> what other languages?</button>
          <button className="fu" onClick={() => ask('run _module_from_relpath on a few example paths')}><span className="arr">↳</span> run it on a few paths</button>
        </div>
      </div>
    </>
  );
}

Object.assign(window, { FrameEmpty, FrameMidStream, FrameA, FrameB, FrameC });
