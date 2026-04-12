# Backend Tree-sitter Integration with Deep Graph Extraction

**Date:** 2026-04-11
**Scope:** Backend analyzer + new parser module + database schema + API endpoints + info panel symbols section (Sub-project A of #4+#3)
**Status:** Approved

## Summary

Replace the regex-based parser in `analyzer.py` with Tree-sitter (Python bindings) for 6 languages: Python, JavaScript, TypeScript, CSS, C++, and Rust. Extract functions, classes, interfaces, traits, enums, imports, call sites, and inheritance relationships. Store in new `symbols` and `symbol_edges` database tables. Module-level graph edges become more accurate (derived from actual symbol calls). Atlas stays module-level; the info panel gains a symbols section via a new `/api/module/symbols` endpoint. Other languages fall back to existing regex-based import extraction.

## Decisions Made

| Question | Choice | Rationale |
|----------|--------|-----------|
| Languages | Python, JS, TS, CSS, C++, Rust (6) | Covers current 3 + 3 commonly requested. Document limitation. |
| Extraction level | Full: definitions, imports, calls, inheritance | Maximum graph richness for consciousness signal |
| Runtime | Backend only (sub-project A) | Browser WASM deferred to sub-project B |
| Database | New `symbols` + `symbol_edges` tables | Clean separation from module-level data |
| Atlas visualization | Module-level default, symbols in info panel on select | Keeps 3D view clean, leverages existing code viewer panel |
| API | Enrich existing + new `/api/module/symbols` | Lean graph endpoint, focused symbols endpoint |

## Database Schema

### New table: `symbols`

```sql
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,       -- 'function', 'class', 'method', 'interface', 'trait', 'enum'
    file_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    parent_symbol_id INTEGER, -- for methods inside classes, nested functions
    module TEXT,              -- which module this symbol belongs to
    UNIQUE(project_id, file_path, name, kind, line_start)
);
```

### New table: `symbol_edges`

```sql
CREATE TABLE IF NOT EXISTS symbol_edges (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    from_symbol_id INTEGER NOT NULL,
    to_symbol_id INTEGER NOT NULL,
    edge_type TEXT NOT NULL,  -- 'calls', 'inherits', 'contains', 'imports'
    UNIQUE(project_id, from_symbol_id, to_symbol_id, edge_type),
    FOREIGN KEY (from_symbol_id) REFERENCES symbols(id),
    FOREIGN KEY (to_symbol_id) REFERENCES symbols(id)
);
```

### Existing tables (unchanged schema, improved data)

- `modules` — same schema. Populated from symbol extraction (unique modules derived from file paths).
- `dependencies` — same schema. Edges now derived from aggregated symbol-level CALLS across modules, not regex import guessing. Edge type remains `'import'` for backward compatibility, but accuracy improves.
- `analysis_file_insights` — same schema. `imports_json` now populated from Tree-sitter extraction. `complexity` derived from AST structure.

## Tree-sitter Parser Module

### New file: `src/copyclip/intelligence/tree_sitter_parser.py`

Responsibilities:
- Initialize Tree-sitter parsers for each supported language
- Define language-specific queries (S-expressions) for extracting definitions, imports, calls, inheritance
- Provide a unified extraction interface: `extract_symbols(content: str, language: str) -> ExtractionResult`

### ExtractionResult type

```python
@dataclass
class SymbolDef:
    name: str
    kind: str           # 'function', 'class', 'method', 'interface', 'trait', 'enum'
    line_start: int
    line_end: int
    parent: str | None  # parent symbol name (for methods inside classes)

@dataclass
class ImportRef:
    target: str         # module/package being imported
    alias: str | None   # local alias if any

@dataclass
class CallRef:
    caller: str         # name of the calling function/method
    callee: str         # name of the called function/method
    line: int

@dataclass
class InheritanceRef:
    child: str          # class name
    parent: str         # parent class/interface name

@dataclass
class ExtractionResult:
    definitions: list[SymbolDef]
    imports: list[ImportRef]
    calls: list[CallRef]
    inheritance: list[InheritanceRef]
    complexity: int     # derived from AST (nesting depth + branch count)
```

### Language-specific queries

Each language needs Tree-sitter S-expression queries for:

**Python:**
- Definitions: `(function_definition name: (identifier) @name)`, `(class_definition name: (identifier) @name)`
- Imports: `(import_statement name: (dotted_name) @name)`, `(import_from_statement module_name: (dotted_name) @name)`
- Calls: `(call function: (identifier) @name)`, `(call function: (attribute) @name)`
- Inheritance: `(class_definition superclasses: (argument_list (identifier) @parent))`

**JavaScript/TypeScript:**
- Definitions: `(function_declaration name: (identifier) @name)`, `(class_declaration name: (identifier) @name)`, `(method_definition name: (property_identifier) @name)`
- Imports: `(import_statement source: (string) @source)`
- Calls: `(call_expression function: (identifier) @name)`, `(call_expression function: (member_expression) @name)`
- Inheritance: `(class_heritage (identifier) @parent)`

**C++:**
- Definitions: `(function_definition declarator: (function_declarator declarator: (identifier) @name))`, `(class_specifier name: (type_identifier) @name)`
- Includes: `(preproc_include path: (_) @path)`
- Calls: `(call_expression function: (identifier) @name)`
- Inheritance: `(base_class_clause (type_identifier) @parent)`

**Rust:**
- Definitions: `(function_item name: (identifier) @name)`, `(struct_item name: (type_identifier) @name)`, `(impl_item trait: (type_identifier) @trait)`, `(trait_item name: (type_identifier) @name)`, `(enum_item name: (type_identifier) @name)`
- Imports: `(use_declaration argument: (_) @path)`
- Calls: `(call_expression function: (identifier) @name)`
- Inheritance: `(impl_item trait: (type_identifier) @trait type: (type_identifier) @type)`

**CSS:**
- Definitions: selectors as symbols (limited — mainly for completeness)
- Imports: `(import_statement (string_value) @path)`
- No calls or inheritance

### Cross-file call resolution

After all files are parsed:

1. **Build global symbol table:** Map `(module, symbol_name)` → `symbol_id` from all `SymbolDef` entries
2. **Build import map:** For each file, map imported names to their source modules using `ImportRef` entries
3. **Resolve calls:** For each `CallRef`, look up the callee in:
   - Same-file symbols first (local scope)
   - Imported symbols via the import map
   - If unresolved, skip (don't create a broken edge)
4. **Create `symbol_edges`:** Insert resolved CALLS, INHERITS, and CONTAINS relationships

### Fallback for unsupported languages

If a file's language is not in the 6 supported languages, fall back to the existing `_extract_import_targets` regex extraction. The file still gets a module assignment and import edges, but no symbol-level data.

## Analyzer Integration

### Changes to `analyzer.py`

The main analysis loop (around line 581) currently does:

```python
if language in {"python", "javascript", "typescript"} and st_size < 300_000:
    content = p.read_text(...)
    cscore = _complexity_score(content, language)
    imports = sorted(_extract_import_targets(content, language))
```

This becomes:

```python
TREE_SITTER_LANGUAGES = {"python", "javascript", "typescript", "css", "cpp", "rust"}

if language in TREE_SITTER_LANGUAGES and st_size < 300_000:
    content = p.read_text(...)
    result = extract_symbols(content, language)
    cscore = result.complexity
    imports = sorted(set(imp.target for imp in result.imports))
    # Store raw extraction for cross-file resolution pass
    file_extractions[rel] = result
elif language in {"python", "javascript", "typescript"} and st_size < 300_000:
    # Fallback to regex for other analyzable languages
    content = p.read_text(...)
    cscore = _complexity_score(content, language)
    imports = sorted(_extract_import_targets(content, language))
```

After the per-file loop, a new **resolution pass** runs:

1. Insert all `SymbolDef` entries into `symbols` table
2. Build global symbol table
3. Resolve `CallRef` entries across files using import map
4. Resolve `InheritanceRef` entries
5. Insert all resolved edges into `symbol_edges` table
6. Update `dependencies` table with more accurate module-level edges (aggregated from symbol CALLS)

### Language detection extension

`_lang_from_ext` needs to handle `.cpp`, `.cc`, `.h`, `.hpp` → `"cpp"` and `.rs` → `"rust"`. Currently only handles Python, JS, TS, CSS.

## API Endpoints

### Modified: `/api/architecture/graph`

Same response shape:
```json
{
  "nodes": [{ "name": "intelligence/server" }],
  "edges": [{ "from": "intelligence/server", "to": "intelligence/db", "type": "import" }]
}
```

But edges are now more accurate — derived from aggregated symbol-level CALLS where available, falling back to import-based edges where Tree-sitter didn't run.

### New: `/api/module/symbols`

```
GET /api/module/symbols?module=intelligence/server
```

Response:
```json
{
  "module": "intelligence/server",
  "symbols": [
    {
      "name": "IntelligenceHandler",
      "kind": "class",
      "file_path": "src/copyclip/intelligence/server.py",
      "line_start": 85,
      "line_end": 2100,
      "methods": ["do_GET", "do_POST", "_json", "_error"],
      "inherits": ["BaseHTTPRequestHandler"]
    },
    {
      "name": "do_GET",
      "kind": "method",
      "file_path": "src/copyclip/intelligence/server.py",
      "line_start": 120,
      "line_end": 1850,
      "calls": ["_json", "with_meta", "build_context_bundle"],
      "called_by": []
    }
  ],
  "meta": { "project": "copyclip", "generated_at": "..." }
}
```

## Frontend: Info Panel Symbols Section

### New state and API call

When a node is selected, fetch `/api/module/symbols` alongside `/api/module/source` (already fetched). Add a symbols section between the connections info and the code viewer.

### Symbols section layout

```
┌─────────────────────────────────┐
│ PERSISTENT LINK ESTABLISHED     │
│ intelligence/server             │
│ [debt] [connections]            │
│ [imports] [dependents]          │
│                                 │
│ SYMBOLS (12 definitions)        │
│ ◆ IntelligenceHandler  class    │
│   ├ do_GET         method       │
│   ├ do_POST        method       │
│   └ _json          method       │
│ ◆ run_server       function     │
│ ◆ _get_project_id  function     │
│                                 │
│ [file tabs]                     │
│ [code viewer]                   │
│ Click deep space to release     │
└─────────────────────────────────┘
```

- Symbols grouped by kind: classes first (with their methods nested), then standalone functions
- Clicking a symbol in the list scrolls the code viewer to that symbol's `line_start`
- Symbol names colored by kind: classes in cyan, functions in white, methods in muted

### Types

```typescript
export type SymbolItem = {
  name: string
  kind: 'function' | 'class' | 'method' | 'interface' | 'trait' | 'enum'
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
  meta?: { project?: string; generated_at?: string }
}
```

## Dependencies

Python packages to add:
- `tree-sitter>=0.21.0`
- `tree-sitter-python`
- `tree-sitter-javascript`
- `tree-sitter-typescript`
- `tree-sitter-css`
- `tree-sitter-cpp`
- `tree-sitter-rust`

## Files Modified/Created

| File | Action | Responsibility |
|------|--------|----------------|
| `src/copyclip/intelligence/tree_sitter_parser.py` | Create | Tree-sitter extraction per language |
| `src/copyclip/intelligence/analyzer.py` | Modify | Replace regex with Tree-sitter, add resolution pass, extend `_lang_from_ext` |
| `src/copyclip/intelligence/db.py` | Modify | Add `symbols` and `symbol_edges` tables |
| `src/copyclip/intelligence/server.py` | Modify | Add `/api/module/symbols`, improve graph edge accuracy |
| `frontend/src/types/api.ts` | Modify | Add `SymbolItem`, `ModuleSymbolsResponse` |
| `frontend/src/api/client.ts` | Modify | Add `moduleSymbols()` method |
| `frontend/src/pages/Atlas3DPage.tsx` | Modify | Add symbols section to info panel, click-to-scroll |
| `frontend/src/styles.css` | Modify | Add symbol list styles |
| `pyproject.toml` or `setup.py` | Modify | Add tree-sitter dependencies |
| `docs/LANGUAGE_SUPPORT.md` | Create | Document supported languages and limitations |

## Documented Limitation

Tree-sitter extraction supports: Python, JavaScript, TypeScript, CSS, C++, and Rust. Files in other languages receive regex-based import extraction only (no function/class-level symbols). Additional languages can be added by implementing a query spec in `tree_sitter_parser.py`.

## What Stays the Same

- Atlas 3D graph rendering (module-level nodes, force-directed layout, node dimming, scaling)
- Augmented-ui panel geometry and existing code viewer
- Module-level cognitive debt calculations
- All other pages and endpoints
- MCP server tools
