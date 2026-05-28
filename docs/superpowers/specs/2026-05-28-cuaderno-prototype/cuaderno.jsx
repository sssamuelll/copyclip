// cuaderno.jsx — single Cuaderno surface
// Exposes <Cuaderno> to window. Props let artboards configure a specific state.

const { useState, useEffect, useRef, useMemo } = React;

const SCENES = {
  empty:     { number: '·',  brief: 'first run' },
  midstream: { number: '02', brief: 'thinking' },
  A:         { number: '01', brief: 'broad' },
  B:         { number: '02', brief: 'relational' },
  C:         { number: '03', brief: 'atomic' },
};

const TOOLS_PRESET = [
  { state: 'done',    name: 'grep_symbols', args: "(file='playground.py')",   ms: 64 },
  { state: 'done',    name: 'read_file',    args: "('playground.py', 1-50)",  ms: 112 },
  { state: 'running', name: 'get_callers',  args: "('resolve_function_ref')", ms: null },
  { state: 'queued',  name: 'read_file',    args: "('analyzer.py', 150-170)", ms: null },
];

function Cuaderno({
  scene = 'A',                  // 'empty' | 'midstream' | 'A' | 'B' | 'C'
  theme = 'light',              // 'light' | 'dark'
  accent = 'sienna',            // 'sienna' | 'ink-blue' | 'forest'
  density = 'regular',          // 'compact' | 'regular' | 'comfy'
  swapAnim = 'fade',            // 'cut' | 'fade' | 'slide'
  sidePanelOpenFor = null,      // path to open by default
  historyOpen = false,
  gotIt = null,                 // null | 'got' | 'didnt'
  showFollowups = true,
  inputValue = '',
  inputPlaceholder = 'ask whatever you want…',
  sessionLabel = '~/code/copyclip · session 14',
  questionNumber = '01 · q',
  interactive = true,
}) {
  const [activeScene, setActiveScene] = useState(scene);
  const [sidePanel, setSidePanel]     = useState(sidePanelOpenFor);
  const [history, setHistory]         = useState(historyOpen);
  const [marker, setMarker]           = useState(gotIt);
  const [input, setInput]             = useState(inputValue);
  const [swapKey, setSwapKey]         = useState(0);

  useEffect(() => { setActiveScene(scene); }, [scene]);
  useEffect(() => { setSidePanel(sidePanelOpenFor); }, [sidePanelOpenFor]);
  useEffect(() => { setHistory(historyOpen); }, [historyOpen]);
  useEffect(() => { setMarker(gotIt); }, [gotIt]);

  const openCite = (path) => setSidePanel(path);
  const closeSide = () => setSidePanel(null);

  const ask = (q) => {
    if (!interactive) return;
    setInput('');
    setMarker(null);
    // pick a scene by keyword
    const lc = q.toLowerCase();
    let next = 'A';
    if (lc.includes('connect') || lc.includes('analyzer and') || lc.includes('cuaderno')) next = 'B';
    else if (lc.includes('slash') || lc.includes('module_from_relpath') || lc.includes('line 152')) next = 'C';
    else if (lc.includes('what does this project')) next = 'A';
    else if (q.trim() === '') return;
    setActiveScene(next);
    setSwapKey(k => k + 1);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim()) ask(input);
  };

  const classes = [
    'cuaderno',
    `theme-${theme}`,
    `accent-${accent}`,
    `density-${density}`,
  ].join(' ');

  const stageClass = `cua-stage swap-${swapAnim}`;

  // session entries (mock)
  const sessionItems = [
    { n: 1, q: 'what does this project do?',                         when: '–14m', bookmarked: false },
    { n: 2, q: 'how do the analyzer and the playground connect?',    when: '–11m', bookmarked: true  },
    { n: 3, q: 'why does _module_from_relpath use slash, not dot?',  when: '–4m',  bookmarked: false, active: true },
    { n: 4, q: 'show me commit a0dae63',                             when: '–2m',  bookmarked: false },
  ];

  return (
    <div className={classes}>
      {/* ── top chrome ─────────────────────────────────────────────────────── */}
      <div className="cua-top">
        <div className="crumb">
          <span className="dot" />
          <span className="here">copyclip</span>
          <span className="sep">·</span>
          <span>cuaderno</span>
          <span className="sep">·</span>
          <span style={{ color: 'var(--ink-2)' }}>{sessionLabel.split(' · ')[0]}</span>
        </div>
        <div className="right">
          <span className="session">{questionNumber}</span>
          <button
            className="hamb"
            onClick={() => interactive && setHistory(h => !h)}
            aria-label="session history"
          >≡</button>
        </div>
      </div>

      {/* ── stage (active frame) ───────────────────────────────────────────── */}
      <div className={stageClass}>
        <div className="cua-frame-wrap">
          <div className="cua-frame" key={swapKey + ':' + activeScene}>
            {activeScene === 'empty'     && <FrameEmpty ask={ask} />}
            {activeScene === 'midstream' && (
              <FrameMidStream
                tools={TOOLS_PRESET}
                partial="The playground reads data that the analyzer wrote. The seam is the"
              />
            )}
            {activeScene === 'A' && <FrameA openCite={openCite} ask={ask} />}
            {activeScene === 'B' && <FrameB openCite={openCite} ask={ask} />}
            {activeScene === 'C' && <FrameC openCite={openCite} ask={ask} />}

            {/* "I got this / I didn't" markers */}
            {activeScene !== 'empty' && activeScene !== 'midstream' && (
              <div className="gotit">
                {marker === null ? (
                  <>
                    <span className="ask">does this answer the question?</span>
                    <button
                      className="gotit-btn"
                      onClick={() => interactive && setMarker('got')}
                    >
                      <span style={{ color: 'var(--accent-2)' }}>✓</span> I got this
                    </button>
                    <button
                      className="gotit-btn"
                      onClick={() => interactive && setMarker('didnt')}
                    >
                      <span style={{ color: 'var(--accent)' }}>↻</span> I didn't
                    </button>
                  </>
                ) : marker === 'got' ? (
                  <>
                    <button className="gotit-btn is-got">✓ marked: got this</button>
                    <span className="gotit-msg">
                      saved to <span style={{ color: 'var(--ink)' }}>this matters</span>. ask anything else when ready.
                    </span>
                  </>
                ) : (
                  <>
                    <button className="gotit-btn is-didnt">↻ marked: didn't</button>
                    <span className="gotit-msg">
                      where did it break? try a follow-up below or rephrase.
                    </span>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ── composer ─────────────────────────────────────────────────────── */}
        <div className="composer-wrap">
          <form className="composer" onSubmit={handleSubmit}>
            <span className="prefix">›</span>
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder={inputPlaceholder}
              disabled={!interactive}
              spellCheck={false}
            />
            <button className="send" type="submit" disabled={!input.trim()}>↵</button>
          </form>
        </div>

        {/* ── side panel (citation viewer) ────────────────────────────────── */}
        {sidePanel && <SidePanel path={sidePanel} onClose={closeSide} />}

        {/* ── history overlay ─────────────────────────────────────────────── */}
        {history && (
          <>
            <div className="history-back" onClick={() => interactive && setHistory(false)} />
            <div className="history">
              <div className="history-head">
                <span>session · this conversation</span>
                <button
                  onClick={() => interactive && setHistory(false)}
                  style={{ background: 'transparent', border: 0, color: 'var(--ink-3)', cursor: 'pointer', fontSize: 14 }}
                >esc</button>
              </div>
              <div className="history-list">
                {sessionItems.map(it => (
                  <button
                    key={it.n}
                    className={'h-item' + (it.bookmarked ? ' bookmarked' : '') + (it.active ? ' active' : '')}
                    onClick={() => {
                      if (!interactive) return;
                      setHistory(false);
                      const next = it.q.toLowerCase().includes('connect') ? 'B'
                                 : it.q.toLowerCase().includes('slash')   ? 'C'
                                 : it.q.toLowerCase().includes('what does') ? 'A'
                                 : 'A';
                      setActiveScene(next);
                      setSwapKey(k => k + 1);
                    }}
                  >
                    <span className="num">{String(it.n).padStart(2, '0')}</span>
                    <span className="q">{it.q}</span>
                    <span className="when">{it.when}</span>
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── SidePanel ────────────────────────────────────────────────────────────────
function SidePanel({ path, onClose }) {
  // strip line range to find file
  const m = path.match(/^([^:]+):(\d+)(?:-(\d+))?$/);
  const isCommit = path.startsWith('commit ');
  let file = path, lineStart = null, lineEnd = null;
  if (m) { file = m[1]; lineStart = parseInt(m[2], 10); lineEnd = m[3] ? parseInt(m[3], 10) : lineStart; }

  const sample = (window.FILE_SAMPLES || {})[file] || (window.FILE_SAMPLES || {})['src/copyclip/intelligence/analyzer.py'];

  if (isCommit) {
    return (
      <>
        <div className="sidepanel-backdrop" onClick={onClose} />
        <div className="sidepanel">
          <div className="sidepanel-head">
            <div className="path">
              <span className="dim">commit</span>
              <span>{path.replace('commit ', '')}</span>
            </div>
            <button className="close" onClick={onClose}>esc</button>
          </div>
          <div className="sidepanel-body" style={{ padding: '20px 24px' }}>
            <div style={{
              fontFamily: 'var(--font-display)',
              fontStyle: 'italic',
              fontSize: 18,
              color: 'var(--ink)',
              marginBottom: 8,
              textWrap: 'pretty',
            }}>
              fix(playground): derive dotted Python from path, not symbols.module
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink-3)', marginBottom: 22 }}>
              you · 2026-04-12 · src/copyclip/intelligence/playground.py
            </div>
            <div className="diff">
              <div><span className="rem">- mod_name = sym["module"].replace("/", ".")</span></div>
              <div><span className="add">+ mod_name = _module_from_file(sym["file_path"])</span></div>
            </div>
          </div>
          <div className="sidepanel-meta">
            <span className="pair"><b>commit </b>{path.replace('commit ', '')}</span>
            <span className="pair"><b>author </b>you</span>
            <span className="pair"><b>+1 </b>−1</span>
          </div>
        </div>
      </>
    );
  }

  // determine which rows to show (centered around highlight)
  const rows = sample.lines;
  const highlight = new Set(sample.highlight || []);
  if (lineStart) {
    for (let n = lineStart; n <= lineEnd; n++) highlight.add(n);
  }

  return (
    <>
      <div className="sidepanel-backdrop" onClick={onClose} />
      <div className="sidepanel">
        <div className="sidepanel-head">
          <div className="path">
            <span className="dim">▸</span>
            <span>{file}</span>
            {lineStart && <span className="dim">:{lineStart}{lineEnd > lineStart ? `-${lineEnd}` : ''}</span>}
          </div>
          <button className="close" onClick={onClose}>esc</button>
        </div>
        <div className="sidepanel-body">
          <div className="file-code">
            {rows.map(r => (
              <div key={r.n} className={'row' + (highlight.has(r.n) ? ' hi' : '')}>
                <div className="lno">{r.n}</div>
                <div>{r.t || ' '}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="sidepanel-meta">
          <span className="pair"><b>blame </b>{sample.blame.commit}</span>
          <span className="pair"><b>by </b>{sample.blame.who}</span>
          <span className="pair"><b>on </b>{sample.blame.when}</span>
        </div>
      </div>
    </>
  );
}

Object.assign(window, { Cuaderno, SidePanel });
