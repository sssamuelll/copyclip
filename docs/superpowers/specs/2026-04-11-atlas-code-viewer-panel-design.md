# Atlas Code Viewer Panel

**Date:** 2026-04-11
**Scope:** Atlas3DPage info panel expansion + new backend endpoint
**Status:** Approved

## Summary

Expand the augmented-ui info panel in Atlas3DPage to include a code viewer section when a node is selected (persistent link). Uses CodeMirror 5.x for syntax-highlighted, read-only code display with a custom cosmic theme adapted to the Atlas palette. A new `/api/module/source` backend endpoint provides the source files for a given module.

## Decisions Made

| Question | Choice | Rationale |
|----------|--------|-----------|
| Panel layout | Toggleable split (expand existing panel) | One unified augmented-ui frame, no extra panels |
| Source endpoint | New `/api/module/source` | Purpose-built, one call with module name |
| Syntax highlighting | CodeMirror 5.x | Already used on landing page, proven aesthetic |
| Theme | Custom cosmic (adapted highcontrast-dark) | Matches Atlas cyan/amber palette |
| Multi-file handling | File tabs | Focused view per file, easy switching |

## Backend: `/api/module/source` Endpoint

### Request

```
GET /api/module/source?module=intelligence/server
```

### Response

```json
{
  "module": "intelligence/server",
  "files": [
    {
      "path": "src/copyclip/intelligence/server.py",
      "content": "#!/usr/bin/env python3\nimport ...",
      "language": "python"
    }
  ],
  "meta": {
    "project": "copyclip",
    "generated_at": "2026-04-11T..."
  }
}
```

### Implementation

Location: `src/copyclip/intelligence/server.py`, in `do_GET` handler.

1. Parse `module` query parameter
2. Query `analysis_file_insights` table: `SELECT DISTINCT path FROM analysis_file_insights WHERE project_id=? AND module=?`
3. Read each file from disk using the project root path
4. Determine language from file extension
5. Return file list with contents
6. Limit: max 10 files per module, max 100KB per file (truncate with `// ... truncated` marker)

### Edge Cases

- Module not found → return `{ module: "...", files: [] }`
- File deleted from disk since last analysis → skip, don't error
- Binary files → skip
- Very large files → truncate at 100KB

## Frontend: Panel States

### Hover State (compact — no change)

```
┌─────────────────────────────────┐
│ READING PROJECT BODY…           │
│ intelligence/server             │
│ ┌─────────────────────────────┐ │
│ │ COGNITIVE_DEBT    72.3%     │ │
│ └─────────────────────────────┘ │
└─────────────────────────────────┘
```

### Selected State (expanded with code)

```
┌─────────────────────────────────┐ (augmented-ui frame)
│ PERSISTENT LINK ESTABLISHED     │
│ intelligence/server             │
│ ┌─────────────────────────────┐ │
│ │ COGNITIVE_DEBT    72.3%     │ │
│ └─────────────────────────────┘ │
│ ┌─────────────────────────────┐ │
│ │ CONNECTIONS                 │ │
│ │ 12 inbound · 8 outbound    │ │
│ └─────────────────────────────┘ │
│ IMPORTS: db | analyzer | agents │
│ DEPENDENTS: mcp_server | main  │
│                                 │
│ ┌──────┬──────────┬───────────┐ │
│ │server│__init__.py│           │ │ ← file tabs
│ ├──────┴──────────┴───────────┤ │
│ │ class IntelligenceHandler:  │ │
│ │   def do_GET(self):         │ │ ← CodeMirror (read-only)
│ │     parsed = urlparse(...)  │ │
│ │     ...                     │ │
│ └─────────────────────────────┘ │
│ Click deep space to release     │
└─────────────────────────────────┘
```

## Frontend: CodeMirror Integration

### CDN Dependencies

Add to `frontend/index.html`:

```html
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.58.1/codemirror.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.58.1/codemirror.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.58.1/mode/python/python.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.58.1/mode/javascript/javascript.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.58.1/mode/css/css.js"></script>
```

### CodeMirror Configuration

```javascript
CodeMirror(container, {
  value: fileContent,
  mode: languageMode,    // 'python', 'javascript', 'css', etc.
  readOnly: true,
  lineNumbers: true,
  theme: 'atlas-cosmic', // custom theme
  scrollbarStyle: 'null', // use native scrollbar
})
```

### Custom Cosmic Theme (`atlas-cosmic`)

Adapted from highcontrast-dark to match Atlas palette:

```css
.cm-s-atlas-cosmic { background: transparent; color: #b5b4b6; }
.cm-s-atlas-cosmic .CodeMirror-gutters { background: transparent; border: none; }
.cm-s-atlas-cosmic .CodeMirror-linenumber { color: rgba(0, 238, 255, 0.2); }
.cm-s-atlas-cosmic .CodeMirror-cursor { border-left-color: #00eeff; }
.cm-s-atlas-cosmic .cm-keyword { color: #00eeff; }
.cm-s-atlas-cosmic .cm-def { color: #fff; }
.cm-s-atlas-cosmic .cm-variable { color: #c7c9d3; }
.cm-s-atlas-cosmic .cm-variable-2 { color: #47cf73; }
.cm-s-atlas-cosmic .cm-string { color: #ffaa00; }
.cm-s-atlas-cosmic .cm-number { color: #2bc7b9; }
.cm-s-atlas-cosmic .cm-comment { color: #4a5568; }
.cm-s-atlas-cosmic .cm-property { color: #5e91f2; }
.cm-s-atlas-cosmic .cm-operator { color: #47cf73; }
.cm-s-atlas-cosmic .cm-meta { color: #00eeff; }
.cm-s-atlas-cosmic .cm-tag { color: #00eeff; }
.cm-s-atlas-cosmic .cm-atom { color: #a3d65a; }
.cm-s-atlas-cosmic .cm-builtin { color: #ae63e4; }
```

### File Tabs

- Tab bar: horizontal list above the CodeMirror editor
- Active tab: bottom border in cyan, text white
- Inactive tabs: text muted, no border
- Tab text: filename only (last segment of path)
- Clicking a tab swaps the CodeMirror content and mode

### Panel Sizing

- Panel width: 380px when expanded (from 320px compact)
- Code section height: fixed 300px with internal scroll
- Max panel height: ~60vh
- Transition: smooth width/height animation on expand/collapse

## API Client

Add to `frontend/src/api/client.ts`:

```typescript
moduleSource: (module: string) => getJSON<ModuleSourceResponse>(
  `/api/module/source?module=${encodeURIComponent(module)}`
),
```

## Types

Add to `frontend/src/types/api.ts`:

```typescript
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
```

## Files Modified

| File | Change |
|------|--------|
| `src/copyclip/intelligence/server.py` | Add `/api/module/source` endpoint in `do_GET` |
| `frontend/index.html` | Add CodeMirror CDN links (CSS + JS + language modes) |
| `frontend/src/types/api.ts` | Add `ModuleSourceFile`, `ModuleSourceResponse` types |
| `frontend/src/api/client.ts` | Add `moduleSource()` method |
| `frontend/src/styles.css` | Add `.atlas-cosmic` CodeMirror theme, file tab styles, expanded panel styles |
| `frontend/src/pages/Atlas3DPage.tsx` | Expand panel on select: fetch source, render file tabs + CodeMirror |

## Files NOT Modified

- Three.js code, force simulation, edge rendering, node dimming — untouched
- Augmented-ui geometry CSS — stays the same (panel just grows taller/wider)
- All other pages and components
- Backend analyzer, database schema — no changes

## Language Mode Mapping

```
.py    → python
.js    → javascript
.ts    → javascript (close enough for read-only display)
.tsx   → javascript
.css   → css
.json  → javascript
other  → null (plain text, no highlighting)
```
