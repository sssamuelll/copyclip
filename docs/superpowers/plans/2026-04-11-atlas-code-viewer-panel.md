# Atlas Code Viewer Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the Atlas augmented-ui info panel to include a CodeMirror-powered code viewer when a node is selected, fed by a new `/api/module/source` backend endpoint.

**Architecture:** Backend adds a single GET endpoint that maps module names to file paths (via `analysis_file_insights`) and reads their contents. Frontend expands the existing augmented-ui panel on select to include file tabs and a read-only CodeMirror instance with a custom cosmic theme.

**Tech Stack:** Python (backend endpoint), CodeMirror 5.58.1 (CDN), TypeScript/React (frontend)

---

### File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/copyclip/intelligence/server.py` | Modify | Add `/api/module/source` endpoint |
| `frontend/index.html` | Modify | Add CodeMirror CDN links |
| `frontend/src/types/api.ts` | Modify | Add `ModuleSourceFile`, `ModuleSourceResponse` |
| `frontend/src/api/client.ts` | Modify | Add `moduleSource()` method |
| `frontend/src/styles.css` | Modify | Add CodeMirror cosmic theme, file tabs, expanded panel styles |
| `frontend/src/pages/Atlas3DPage.tsx` | Modify | Expand panel with code viewer, file tabs, CodeMirror init |

---

### Task 1: Backend `/api/module/source` endpoint

**Files:**
- Modify: `src/copyclip/intelligence/server.py` — add new endpoint block after `/api/files` (after line 690)

- [ ] **Step 1: Add the endpoint**

In `src/copyclip/intelligence/server.py`, find the block ending at line 690:

```python
                }))
                return

            if parsed.path == "/api/context-bundle":
```

Insert the new endpoint between `/api/files` and `/api/context-bundle`. Add this code before the `if parsed.path == "/api/context-bundle":` line:

```python
            if parsed.path == "/api/module/source":
                if not pid:
                    self._json(with_meta({"module": "", "files": []}))
                    return
                q = parse_qs(parsed.query or "")
                module_name = (q.get("module", [""])[0] or "").strip()
                if not module_name:
                    self._json(with_meta({"module": "", "files": []}))
                    return
                rows = conn.execute(
                    "SELECT DISTINCT path FROM analysis_file_insights WHERE project_id=? AND module=? LIMIT 10",
                    (pid, module_name),
                ).fetchall()
                result_files = []
                root_path = Path(root).resolve()
                for (rel_path,) in rows:
                    fp = (root_path / rel_path).resolve()
                    if not fp.is_relative_to(root_path) or not fp.exists() or not fp.is_file():
                        continue
                    try:
                        raw = fp.read_bytes()
                        if b"\x00" in raw[:1024]:
                            continue  # skip binary
                        content = raw.decode("utf-8", errors="replace")
                        if len(content) > 102400:
                            content = content[:102400] + "\n// ... truncated (100KB limit)"
                        ext = fp.suffix.lstrip(".")
                        lang_map = {"py": "python", "js": "javascript", "ts": "javascript", "tsx": "javascript", "css": "css", "json": "javascript"}
                        result_files.append({"path": rel_path, "content": content, "language": lang_map.get(ext, "")})
                    except Exception:
                        continue
                self._json(with_meta({"module": module_name, "files": result_files}))
                return

```

- [ ] **Step 2: Verify the `Path` import exists**

Check the top of `server.py` for `from pathlib import Path`. It's already used at line 1972, so the import exists. No change needed.

- [ ] **Step 3: Test manually**

Start the server and test with curl:

```bash
curl -s "http://localhost:4310/api/module/source?module=copyclip" | python3 -m json.tool | head -30
```

Expected: JSON with `module`, `files` array containing `path`, `content`, `language` fields.

- [ ] **Step 4: Commit**

```bash
git add src/copyclip/intelligence/server.py
git commit -m "feat(api): add /api/module/source endpoint (#12)"
```

---

### Task 2: Add CodeMirror CDN to index.html

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Add CodeMirror CDN links**

Find:

```html
    <link rel="stylesheet" href="https://unpkg.com/augmented-ui@2.0.0/augmented-ui.min.css">
  </head>
```

Replace with:

```html
    <link rel="stylesheet" href="https://unpkg.com/augmented-ui@2.0.0/augmented-ui.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.58.1/codemirror.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.58.1/codemirror.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.58.1/mode/python/python.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.58.1/mode/javascript/javascript.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.58.1/mode/css/css.js"></script>
  </head>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/index.html
git commit -m "build: add CodeMirror 5.58.1 CDN to frontend (#12)"
```

---

### Task 3: Add TypeScript types and API client method

**Files:**
- Modify: `frontend/src/types/api.ts` — add types after `ArchEdge` (line 157)
- Modify: `frontend/src/api/client.ts` — add method before closing `}`

- [ ] **Step 1: Add types**

In `frontend/src/types/api.ts`, find:

```typescript
export type ArchEdge = { from: string; to: string; type: string }

export type ArchaeologyCommit = {
```

Insert between them:

```typescript
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

export type ArchaeologyCommit = {
```

- [ ] **Step 2: Add API method**

In `frontend/src/api/client.ts`, find:

```typescript
  assembleContext: (p: ContextPayload) => postJSON<{ context: string; warnings: string[] }>('/api/assemble-context', p)
}
```

Replace with:

```typescript
  assembleContext: (p: ContextPayload) => postJSON<{ context: string; warnings: string[] }>('/api/assemble-context', p),
  moduleSource: (module: string) => getJSON<ModuleSourceResponse>(`/api/module/source?module=${encodeURIComponent(module)}`),
}
```

Also add the import. Find:

```typescript
import type { ArchNode, ArchEdge, CognitiveLoadItem } from '../types/api'
```

This import is in `Atlas3DPage.tsx`, not `client.ts`. In `client.ts`, find the existing import line at the top and add `ModuleSourceResponse`. The import line will vary — look for the `import type` from `'../types/api'` and add `ModuleSourceResponse` to it.

- [ ] **Step 3: Build to verify types compile**

```bash
cd frontend && npm run build
```

Expected: Clean build.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/client.ts
git commit -m "feat(api): add moduleSource client method and types (#12)"
```

---

### Task 4: Add CodeMirror cosmic theme and panel styles

**Files:**
- Modify: `frontend/src/styles.css` — add styles before the `@media` block

- [ ] **Step 1: Add the cosmic theme and panel styles**

In `frontend/src/styles.css`, find:

```css
@media (max-width: 1200px) {
```

Insert before it:

```css
/* --- Atlas Code Viewer --- */
.atlas-info-panel--locked {
  width: 380px;
  max-height: 60vh;
  overflow-y: auto;
}

.atlas-file-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #222;
  margin-bottom: 0;
  overflow-x: auto;
}

.atlas-file-tab {
  padding: 6px 12px;
  font-size: 10px;
  color: #666;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
  transition: color 0.15s ease, border-color 0.15s ease;
  font-family: 'IBM Plex Mono', monospace;
}

.atlas-file-tab:hover {
  color: #aaa;
}

.atlas-file-tab--active {
  color: #fff;
  border-bottom-color: #00eeff;
}

.atlas-code-container {
  height: 300px;
  overflow: hidden;
  border: 1px solid #222;
  background: rgba(0, 0, 0, 0.3);
}

.atlas-code-container .CodeMirror {
  height: 100%;
  background: transparent;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
}

/* CodeMirror Atlas Cosmic Theme */
.cm-s-atlas-cosmic { background: transparent; color: #b5b4b6; }
.cm-s-atlas-cosmic .CodeMirror-gutters { background: transparent; border: none; margin-right: 8px; }
.cm-s-atlas-cosmic .CodeMirror-linenumber { color: rgba(0, 238, 255, 0.2); padding-right: 8px; }
.cm-s-atlas-cosmic .CodeMirror-cursor { border-left-color: #00eeff !important; }
.cm-s-atlas-cosmic .CodeMirror-selected { background: rgba(0, 238, 255, 0.1); }
.cm-s-atlas-cosmic .cm-keyword { color: #00eeff; }
.cm-s-atlas-cosmic .cm-def { color: #fff; }
.cm-s-atlas-cosmic .cm-variable { color: #c7c9d3; }
.cm-s-atlas-cosmic .cm-variable-2 { color: #47cf73; }
.cm-s-atlas-cosmic .cm-string { color: #ffaa00; }
.cm-s-atlas-cosmic .cm-string-2 { color: #d75093; }
.cm-s-atlas-cosmic .cm-number { color: #2bc7b9; }
.cm-s-atlas-cosmic .cm-comment { color: #4a5568; }
.cm-s-atlas-cosmic .cm-property { color: #5e91f2; }
.cm-s-atlas-cosmic .cm-operator { color: #47cf73; }
.cm-s-atlas-cosmic .cm-meta { color: #00eeff; }
.cm-s-atlas-cosmic .cm-tag { color: #00eeff; }
.cm-s-atlas-cosmic .cm-atom { color: #a3d65a; }
.cm-s-atlas-cosmic .cm-builtin { color: #ae63e4; }
.cm-s-atlas-cosmic .cm-qualifier { color: #00eeff; }
.cm-s-atlas-cosmic .cm-header { color: #ff3c41; font-weight: bold; }

```

- [ ] **Step 2: Update the existing `.atlas-info-panel--locked` rule**

The existing `.atlas-info-panel--locked` in `styles.css` only has `box-shadow`. We need to merge the new width/height into it. Find:

```css
.atlas-info-panel--locked {
  box-shadow: 0 0 40px rgba(0, 238, 255, 0.15);
}
```

Replace with:

```css
.atlas-info-panel--locked {
  width: 380px;
  max-height: 60vh;
  overflow-y: auto;
  box-shadow: 0 0 40px rgba(0, 238, 255, 0.15);
  transition: width 0.2s ease, max-height 0.2s ease;
}
```

Remove the duplicate `.atlas-info-panel--locked` from the new block added in Step 1 (it was included there for context but the existing rule should be updated instead).

- [ ] **Step 3: Build to verify**

```bash
cd frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/styles.css
git commit -m "style: add CodeMirror cosmic theme and file tab styles (#12)"
```

---

### Task 5: Expand Atlas3DPage panel with code viewer

**Files:**
- Modify: `frontend/src/pages/Atlas3DPage.tsx`

This is the main integration task. The panel expands on select to show file tabs + CodeMirror.

- [ ] **Step 1: Add imports and state**

At the top of the file, update the import from `../types/api`:

Find:

```typescript
import type { ArchNode, ArchEdge, CognitiveLoadItem } from '../types/api'
```

Replace with:

```typescript
import type { ArchNode, ArchEdge, CognitiveLoadItem, ModuleSourceFile } from '../types/api'
```

Add new state variables inside the `Atlas3DPage` component, after the existing `useState` calls:

Find:

```typescript
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [hoveredNodeData, setHoveredNodeData] = useState<GraphNode | null>(null)
```

Replace with:

```typescript
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [hoveredNodeData, setHoveredNodeData] = useState<GraphNode | null>(null)
  const [sourceFiles, setSourceFiles] = useState<ModuleSourceFile[]>([])
  const [activeFileIdx, setActiveFileIdx] = useState(0)
  const [loadingSource, setLoadingSource] = useState(false)
  const codeMirrorRef = useRef<HTMLDivElement>(null)
  const cmInstanceRef = useRef<any>(null)
```

- [ ] **Step 2: Add source fetch effect**

Add a `useEffect` that fetches module source when `selectedNode` changes. Place this after the main `useEffect` block (after the closing `}, [])`):

Find:

```typescript
  }, [])

  const activeNode = selectedNode || hoveredNodeData
```

Replace with:

```typescript
  }, [])

  // Fetch source code when a node is selected
  useEffect(() => {
    if (!selectedNode) {
      setSourceFiles([])
      setActiveFileIdx(0)
      if (cmInstanceRef.current) {
        cmInstanceRef.current.toTextArea()
        cmInstanceRef.current = null
      }
      return
    }
    setLoadingSource(true)
    api.moduleSource(selectedNode.name)
      .then(res => {
        setSourceFiles(res.files || [])
        setActiveFileIdx(0)
        setLoadingSource(false)
      })
      .catch(() => {
        setSourceFiles([])
        setLoadingSource(false)
      })
  }, [selectedNode])

  // Initialize/update CodeMirror when active file changes
  useEffect(() => {
    if (!selectedNode || sourceFiles.length === 0) return
    const file = sourceFiles[activeFileIdx]
    if (!file) return

    // Wait for the DOM container to mount
    const timer = setTimeout(() => {
      const container = codeMirrorRef.current
      if (!container) return

      // Destroy previous instance
      if (cmInstanceRef.current) {
        cmInstanceRef.current.toTextArea()
        cmInstanceRef.current = null
      }

      // Clear container and create textarea
      while (container.firstChild) container.removeChild(container.firstChild)
      const textarea = document.createElement('textarea')
      container.appendChild(textarea)

      // Create CodeMirror
      const CM = (window as any).CodeMirror
      if (!CM) return
      cmInstanceRef.current = CM.fromTextArea(textarea, {
        value: file.content,
        mode: file.language || null,
        readOnly: true,
        lineNumbers: true,
        theme: 'atlas-cosmic',
      })
      cmInstanceRef.current.setValue(file.content)
    }, 50)

    return () => clearTimeout(timer)
  }, [selectedNode, sourceFiles, activeFileIdx])

  const activeNode = selectedNode || hoveredNodeData
```

- [ ] **Step 3: Update the JSX panel to include code viewer**

Find the entire selected-node info section ending with the release hint:

```typescript
            {selectedNode && (
              <div style={{ fontSize: 11, color: '#00eeff', opacity: 0.6 }}>
                Click in deep space to release focus.
              </div>
            )}
          </div>
        </div>
```

Replace with:

```typescript
            {selectedNode && sourceFiles.length > 0 && (
              <>
                <div className="atlas-file-tabs">
                  {sourceFiles.map((f, i) => (
                    <div
                      key={f.path}
                      className={`atlas-file-tab${i === activeFileIdx ? ' atlas-file-tab--active' : ''}`}
                      onClick={() => setActiveFileIdx(i)}
                    >
                      {f.path.split('/').pop()}
                    </div>
                  ))}
                </div>
                <div className="atlas-code-container" ref={codeMirrorRef} />
              </>
            )}
            {selectedNode && loadingSource && sourceFiles.length === 0 && (
              <div style={{ fontSize: 10, color: '#666', padding: 12 }}>Loading source...</div>
            )}
            {selectedNode && (
              <div style={{ fontSize: 11, color: '#00eeff', opacity: 0.6, marginTop: 4 }}>
                Click in deep space to release focus.
              </div>
            )}
          </div>
        </div>
```

- [ ] **Step 4: Build and verify**

```bash
cd frontend && npm run build
```

Expected: Clean build.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Atlas3DPage.tsx
git commit -m "feat(atlas): add code viewer panel with CodeMirror and file tabs (#12)"
```

---

### Task 6: Final build, sync, and verify

- [ ] **Step 1: Final build and sync**

```bash
cd frontend && npm run build && cp dist/index.html ../src/copyclip/intelligence/ui/index.html
```

- [ ] **Step 2: Full manual test**

Run `copyclip start`, open Atlas. Verify:

1. Hovering a node shows the compact info panel (no code section)
2. Clicking a node expands the panel — info section on top, file tabs + code below
3. Code is syntax-highlighted with the cosmic theme (cyan keywords, amber strings)
4. Clicking different file tabs switches the code content
5. Scrolling works within the code section
6. Clicking deep space collapses back to no panel
7. Hovering again shows compact panel (no code, no leftover state)
8. All existing Atlas features still work (force graph, node dimming, edges, scaling)

- [ ] **Step 3: Commit bundle**

```bash
git add src/copyclip/intelligence/ui/index.html
git commit -m "build(ui): sync atlas bundle with code viewer panel (#12)"
```
