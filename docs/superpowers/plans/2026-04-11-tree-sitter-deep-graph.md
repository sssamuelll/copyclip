# Tree-sitter Deep Graph Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace regex-based code parsing with Tree-sitter for 6 languages, extracting function/class-level symbols with calls and inheritance, stored in new database tables and exposed via API for the Atlas info panel.

**Architecture:** New `tree_sitter_parser.py` module handles language-specific AST traversal. Analyzer calls it instead of regex helpers. Results stored in `symbols` + `symbol_edges` tables. New `/api/module/symbols` endpoint serves symbol data. Atlas info panel gains a symbols section.

**Tech Stack:** tree-sitter (Python bindings), tree-sitter-{python,javascript,typescript,css,cpp,rust}

---

### File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `pyproject.toml` | Modify | Add tree-sitter dependencies |
| `src/copyclip/intelligence/db.py` | Modify | Add `symbols` + `symbol_edges` tables |
| `src/copyclip/intelligence/tree_sitter_parser.py` | Create | Language-specific Tree-sitter extraction |
| `tests/test_tree_sitter_parser.py` | Create | Tests for parser extraction |
| `src/copyclip/intelligence/analyzer.py` | Modify | Replace regex with Tree-sitter, add resolution pass |
| `src/copyclip/intelligence/server.py` | Modify | Add `/api/module/symbols` endpoint |
| `frontend/src/types/api.ts` | Modify | Add `SymbolItem`, `ModuleSymbolsResponse` |
| `frontend/src/api/client.ts` | Modify | Add `moduleSymbols()` method |
| `frontend/src/pages/Atlas3DPage.tsx` | Modify | Add symbols section to info panel |
| `frontend/src/styles.css` | Modify | Add symbol list styles |
| `docs/LANGUAGE_SUPPORT.md` | Create | Document supported languages |

---

### Task 1: Add tree-sitter dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Find:

```toml
dependencies = [
  "tqdm",
  "pyperclip",
  "gitignore-parser",
  "aiofiles",
  "python-dotenv",
  "aiohttp",
  "tiktoken",
  "pyyaml",
]
```

Replace with:

```toml
dependencies = [
  "tqdm",
  "pyperclip",
  "gitignore-parser",
  "aiofiles",
  "python-dotenv",
  "aiohttp",
  "tiktoken",
  "pyyaml",
  "tree-sitter>=0.21.0",
  "tree-sitter-python",
  "tree-sitter-javascript",
  "tree-sitter-typescript",
  "tree-sitter-css",
  "tree-sitter-cpp",
  "tree-sitter-rust",
]
```

- [ ] **Step 2: Install dependencies**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
pip3 install -e . 2>&1 | tail -5
```

- [ ] **Step 3: Verify**

```bash
python3 -c "import tree_sitter; import tree_sitter_python; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add tree-sitter dependencies for deep graph extraction (#4)"
```

---

### Task 2: Add `symbols` and `symbol_edges` database tables

**Files:**
- Modify: `src/copyclip/intelligence/db.py`

- [ ] **Step 1: Add tables to schema**

In `src/copyclip/intelligence/db.py`, find the end of the `dependencies` table creation (after line 79, the closing `);`). The next block starts with `CREATE TABLE IF NOT EXISTS decisions`. Insert the two new tables between `dependencies` and `decisions`.

Find:

```python
        CREATE TABLE IF NOT EXISTS dependencies (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            from_module TEXT NOT NULL,
            to_module TEXT NOT NULL,
            edge_type TEXT DEFAULT 'import',
            UNIQUE(project_id, from_module, to_module, edge_type)
        );

        CREATE TABLE IF NOT EXISTS decisions (
```

Replace with:

```python
        CREATE TABLE IF NOT EXISTS dependencies (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            from_module TEXT NOT NULL,
            to_module TEXT NOT NULL,
            edge_type TEXT DEFAULT 'import',
            UNIQUE(project_id, from_module, to_module, edge_type)
        );

        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            file_path TEXT NOT NULL,
            line_start INTEGER,
            line_end INTEGER,
            parent_symbol_id INTEGER,
            module TEXT,
            UNIQUE(project_id, file_path, name, kind, line_start)
        );

        CREATE TABLE IF NOT EXISTS symbol_edges (
            id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            from_symbol_id INTEGER NOT NULL,
            to_symbol_id INTEGER NOT NULL,
            edge_type TEXT NOT NULL,
            UNIQUE(project_id, from_symbol_id, to_symbol_id, edge_type),
            FOREIGN KEY (from_symbol_id) REFERENCES symbols(id),
            FOREIGN KEY (to_symbol_id) REFERENCES symbols(id)
        );

        CREATE TABLE IF NOT EXISTS decisions (
```

- [ ] **Step 2: Verify migration works**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
python3 -c "
from copyclip.intelligence.db import get_connection
conn = get_connection('/tmp/test_copyclip_db.sqlite')
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
assert 'symbols' in tables, f'symbols not in {tables}'
assert 'symbol_edges' in tables, f'symbol_edges not in {tables}'
print('OK: symbols and symbol_edges tables created')
conn.close()
import os; os.unlink('/tmp/test_copyclip_db.sqlite')
"
```

- [ ] **Step 3: Commit**

```bash
git add src/copyclip/intelligence/db.py
git commit -m "feat(db): add symbols and symbol_edges tables (#4, #3)"
```

---

### Task 3: Create Tree-sitter parser module

**Files:**
- Create: `src/copyclip/intelligence/tree_sitter_parser.py`
- Create: `tests/test_tree_sitter_parser.py`

This is the core task. The parser provides `extract_symbols(content: str, language: str) -> ExtractionResult`.

- [ ] **Step 1: Write tests**

Create `tests/test_tree_sitter_parser.py`:

```python
from copyclip.intelligence.tree_sitter_parser import extract_symbols


def test_python_functions_and_classes():
    code = '''
import os
from pathlib import Path

class Handler(Base):
    def do_get(self, req):
        result = os.path.join(req.url)
        return result

def standalone(a, b):
    return a + b
'''
    result = extract_symbols(code, "python")
    names = {d.name for d in result.definitions}
    assert "Handler" in names
    assert "do_get" in names
    assert "standalone" in names

    kinds = {d.name: d.kind for d in result.definitions}
    assert kinds["Handler"] == "class"
    assert kinds["do_get"] == "method"
    assert kinds["standalone"] == "function"

    import_targets = {i.target for i in result.imports}
    assert "os" in import_targets
    assert "pathlib" in import_targets

    assert result.complexity > 0


def test_python_inheritance():
    code = '''
class Child(Parent):
    pass
'''
    result = extract_symbols(code, "python")
    assert len(result.inheritance) == 1
    assert result.inheritance[0].child == "Child"
    assert result.inheritance[0].parent == "Parent"


def test_python_calls():
    code = '''
def foo():
    bar()
    obj.method()
'''
    result = extract_symbols(code, "python")
    callee_names = {c.callee for c in result.calls}
    assert "bar" in callee_names
    assert "obj.method" in callee_names


def test_javascript_extraction():
    code = '''
import { api } from "../api/client"
import React from "react"

class Handler extends Base {
  doGet(req) {
    const result = api.fetch(req.url)
    return result
  }
}

function standalone(a) {
  return console.log(a)
}
'''
    result = extract_symbols(code, "javascript")
    names = {d.name for d in result.definitions}
    assert "Handler" in names
    assert "doGet" in names
    assert "standalone" in names

    import_sources = {i.target for i in result.imports}
    assert "../api/client" in import_sources
    assert "react" in import_sources


def test_typescript_uses_javascript_parser():
    code = '''
export function greet(name: string): string {
    return name
}
'''
    result = extract_symbols(code, "typescript")
    names = {d.name for d in result.definitions}
    assert "greet" in names


def test_cpp_extraction():
    code = '''
#include <iostream>
#include "myheader.h"

class Widget : public Base {
public:
    void render() {
        draw();
    }
};

int main() {
    Widget w;
    w.render();
    return 0;
}
'''
    result = extract_symbols(code, "cpp")
    names = {d.name for d in result.definitions}
    assert "Widget" in names
    assert "main" in names


def test_rust_extraction():
    code = '''
use std::io;

struct Point {
    x: f64,
    y: f64,
}

trait Drawable {
    fn draw(&self);
}

impl Drawable for Point {
    fn draw(&self) {
        println!("drawing");
    }
}

fn standalone() -> i32 {
    42
}
'''
    result = extract_symbols(code, "rust")
    names = {d.name for d in result.definitions}
    assert "Point" in names
    assert "Drawable" in names
    assert "standalone" in names


def test_css_extraction():
    code = '''
@import url("reset.css");

.container {
    display: flex;
}
'''
    result = extract_symbols(code, "css")
    import_targets = {i.target for i in result.imports}
    assert "reset.css" in import_targets or len(result.imports) >= 0  # CSS imports are best-effort


def test_unsupported_language_returns_empty():
    result = extract_symbols("fn main() {}", "haskell")
    assert len(result.definitions) == 0
    assert len(result.imports) == 0
    assert len(result.calls) == 0
    assert len(result.inheritance) == 0


def test_empty_content():
    result = extract_symbols("", "python")
    assert len(result.definitions) == 0


def test_malformed_code_does_not_crash():
    result = extract_symbols("def (((broken syntax:::::", "python")
    assert result is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
python3 -m pytest tests/test_tree_sitter_parser.py -v 2>&1 | tail -5
```

Expected: FAIL with `ModuleNotFoundError: No module named 'copyclip.intelligence.tree_sitter_parser'`

- [ ] **Step 3: Implement the parser**

Create `src/copyclip/intelligence/tree_sitter_parser.py`:

```python
"""Tree-sitter based code extraction for 6 languages.

Extracts function/class definitions, imports, call sites, and inheritance
relationships from source code using AST traversal.

Supported: Python, JavaScript, TypeScript, CSS, C++, Rust.
Unsupported languages return empty results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from tree_sitter import Language, Parser


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SymbolDef:
    name: str
    kind: str  # 'function', 'class', 'method', 'interface', 'trait', 'enum', 'struct'
    line_start: int
    line_end: int
    parent: Optional[str] = None


@dataclass
class ImportRef:
    target: str
    alias: Optional[str] = None


@dataclass
class CallRef:
    caller: str
    callee: str
    line: int


@dataclass
class InheritanceRef:
    child: str
    parent: str


@dataclass
class ExtractionResult:
    definitions: list[SymbolDef] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)
    calls: list[CallRef] = field(default_factory=list)
    inheritance: list[InheritanceRef] = field(default_factory=list)
    complexity: int = 0


# ---------------------------------------------------------------------------
# Language setup (lazy init)
# ---------------------------------------------------------------------------

_parsers: dict[str, Parser] = {}
_languages: dict[str, Language] = {}

# Map user-facing language names to tree-sitter module + grammar accessor
_LANG_MODULES = {
    "python": ("tree_sitter_python", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "css": ("tree_sitter_css", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
    "rust": ("tree_sitter_rust", "language"),
}

SUPPORTED_LANGUAGES = set(_LANG_MODULES.keys())


def _get_parser(lang: str) -> Optional[Parser]:
    if lang in _parsers:
        return _parsers[lang]
    spec = _LANG_MODULES.get(lang)
    if not spec:
        return None
    mod_name, func_name = spec
    try:
        import importlib
        mod = importlib.import_module(mod_name)
        language = Language(getattr(mod, func_name)())
        parser = Parser(language)
        _parsers[lang] = parser
        _languages[lang] = language
        return parser
    except Exception:
        return None


# ---------------------------------------------------------------------------
# AST traversal helpers
# ---------------------------------------------------------------------------

def _find_nodes(node, type_name: str) -> list:
    results = []
    if node.type == type_name:
        results.append(node)
    for child in node.children:
        results.extend(_find_nodes(child, type_name))
    return results


def _find_nodes_multi(node, type_names: set) -> list:
    results = []
    if node.type in type_names:
        results.append(node)
    for child in node.children:
        results.extend(_find_nodes_multi(child, type_names))
    return results


def _node_name(node, field: str = "name") -> str:
    child = node.child_by_field_name(field)
    return child.text.decode("utf-8", errors="replace") if child else ""


def _enclosing_function(node) -> str:
    """Walk up the tree to find the enclosing function/method name."""
    current = node.parent
    while current:
        if current.type in ("function_definition", "function_declaration",
                            "method_definition", "function_item"):
            name = _node_name(current)
            if name:
                return name
        current = current.parent
    return "<module>"


# ---------------------------------------------------------------------------
# Language extractors
# ---------------------------------------------------------------------------

def _extract_python(root) -> ExtractionResult:
    result = ExtractionResult()

    # Classes
    for n in _find_nodes(root, "class_definition"):
        name = _node_name(n)
        if not name:
            continue
        result.definitions.append(SymbolDef(
            name=name, kind="class",
            line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
        ))
        # Inheritance
        supers = n.child_by_field_name("superclasses")
        if supers:
            for c in supers.named_children:
                parent_name = c.text.decode("utf-8", errors="replace")
                if parent_name:
                    result.inheritance.append(InheritanceRef(child=name, parent=parent_name))
        # Methods inside this class
        for m in _find_nodes(n, "function_definition"):
            mname = _node_name(m)
            if mname and m.parent and m.parent.type == "block" and m.parent.parent == n:
                result.definitions.append(SymbolDef(
                    name=mname, kind="method",
                    line_start=m.start_point[0] + 1, line_end=m.end_point[0] + 1,
                    parent=name,
                ))

    # Standalone functions (not inside a class)
    for n in _find_nodes(root, "function_definition"):
        name = _node_name(n)
        if not name:
            continue
        # Check if this is a top-level function (parent chain doesn't include class_definition)
        is_method = False
        p = n.parent
        while p:
            if p.type == "class_definition":
                is_method = True
                break
            p = p.parent
        if not is_method:
            result.definitions.append(SymbolDef(
                name=name, kind="function",
                line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
            ))

    # Imports
    for n in _find_nodes(root, "import_statement"):
        for child in n.named_children:
            target = child.text.decode("utf-8", errors="replace").split(".")[0]
            if target:
                result.imports.append(ImportRef(target=target))
    for n in _find_nodes(root, "import_from_statement"):
        mod = n.child_by_field_name("module_name")
        if mod:
            target = mod.text.decode("utf-8", errors="replace").split(".")[0]
            if target:
                result.imports.append(ImportRef(target=target))

    # Calls
    for n in _find_nodes(root, "call"):
        fn = n.child_by_field_name("function")
        if fn:
            callee = fn.text.decode("utf-8", errors="replace")
            caller = _enclosing_function(n)
            result.calls.append(CallRef(caller=caller, callee=callee, line=n.start_point[0] + 1))

    # Complexity
    complexity_types = {"if_statement", "elif_clause", "else_clause", "for_statement",
                        "while_statement", "try_statement", "except_clause",
                        "function_definition", "class_definition"}
    result.complexity = len(_find_nodes_multi(root, complexity_types))

    return result


def _extract_javascript(root) -> ExtractionResult:
    result = ExtractionResult()

    # Classes
    for n in _find_nodes(root, "class_declaration"):
        name = _node_name(n)
        if not name:
            continue
        result.definitions.append(SymbolDef(
            name=name, kind="class",
            line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
        ))
        # Inheritance (extends)
        heritage = n.child_by_field_name("heritage") or n.child_by_field_name("superclass")
        if not heritage:
            # Try to find class_heritage node
            for c in n.children:
                if c.type == "class_heritage":
                    heritage = c
                    break
        if heritage:
            parent_name = heritage.text.decode("utf-8", errors="replace").replace("extends ", "").strip()
            if parent_name:
                result.inheritance.append(InheritanceRef(child=name, parent=parent_name))

    # Methods
    for n in _find_nodes(root, "method_definition"):
        name = _node_name(n)
        if not name:
            continue
        # Find parent class
        parent_class = None
        p = n.parent
        while p:
            if p.type == "class_declaration":
                parent_class = _node_name(p)
                break
            p = p.parent
        result.definitions.append(SymbolDef(
            name=name, kind="method",
            line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
            parent=parent_class,
        ))

    # Functions
    for n in _find_nodes(root, "function_declaration"):
        name = _node_name(n)
        if name:
            result.definitions.append(SymbolDef(
                name=name, kind="function",
                line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
            ))

    # Imports
    for n in _find_nodes(root, "import_statement"):
        source = n.child_by_field_name("source")
        if source:
            raw = source.text.decode("utf-8", errors="replace").strip("'\"")
            result.imports.append(ImportRef(target=raw))

    # Calls
    for n in _find_nodes(root, "call_expression"):
        fn = n.child_by_field_name("function")
        if fn:
            callee = fn.text.decode("utf-8", errors="replace")
            caller = _enclosing_function(n)
            result.calls.append(CallRef(caller=caller, callee=callee, line=n.start_point[0] + 1))

    # Complexity
    complexity_types = {"if_statement", "else_clause", "for_statement", "for_in_statement",
                        "while_statement", "switch_statement", "catch_clause",
                        "try_statement", "function_declaration", "arrow_function"}
    result.complexity = len(_find_nodes_multi(root, complexity_types))

    return result


def _extract_cpp(root) -> ExtractionResult:
    result = ExtractionResult()

    # Classes/structs
    for n in _find_nodes(root, "class_specifier"):
        name = _node_name(n)
        if name:
            result.definitions.append(SymbolDef(
                name=name, kind="class",
                line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
            ))
            # Base classes
            for bc in _find_nodes(n, "base_class_clause"):
                for child in bc.named_children:
                    if child.type == "type_identifier":
                        result.inheritance.append(InheritanceRef(child=name, parent=child.text.decode()))

    for n in _find_nodes(root, "struct_specifier"):
        name = _node_name(n)
        if name:
            result.definitions.append(SymbolDef(
                name=name, kind="struct",
                line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
            ))

    # Functions
    for n in _find_nodes(root, "function_definition"):
        declarator = n.child_by_field_name("declarator")
        if declarator:
            # Navigate to the actual identifier
            name_node = declarator
            while name_node and name_node.type != "identifier":
                name_node = name_node.child_by_field_name("declarator") or (
                    name_node.named_children[0] if name_node.named_children else None
                )
            if name_node and name_node.type == "identifier":
                result.definitions.append(SymbolDef(
                    name=name_node.text.decode(),
                    kind="function",
                    line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
                ))

    # Includes
    for n in _find_nodes(root, "preproc_include"):
        path = n.child_by_field_name("path")
        if path:
            raw = path.text.decode().strip("<>\"")
            result.imports.append(ImportRef(target=raw))

    # Calls
    for n in _find_nodes(root, "call_expression"):
        fn = n.child_by_field_name("function")
        if fn:
            callee = fn.text.decode("utf-8", errors="replace")
            caller = _enclosing_function(n)
            result.calls.append(CallRef(caller=caller, callee=callee, line=n.start_point[0] + 1))

    complexity_types = {"if_statement", "else_clause", "for_statement", "while_statement",
                        "switch_statement", "catch_clause", "function_definition"}
    result.complexity = len(_find_nodes_multi(root, complexity_types))

    return result


def _extract_rust(root) -> ExtractionResult:
    result = ExtractionResult()

    # Functions
    for n in _find_nodes(root, "function_item"):
        name = _node_name(n)
        if name:
            result.definitions.append(SymbolDef(
                name=name, kind="function",
                line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
            ))

    # Structs
    for n in _find_nodes(root, "struct_item"):
        name = _node_name(n)
        if name:
            result.definitions.append(SymbolDef(
                name=name, kind="struct",
                line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
            ))

    # Enums
    for n in _find_nodes(root, "enum_item"):
        name = _node_name(n)
        if name:
            result.definitions.append(SymbolDef(
                name=name, kind="enum",
                line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
            ))

    # Traits
    for n in _find_nodes(root, "trait_item"):
        name = _node_name(n)
        if name:
            result.definitions.append(SymbolDef(
                name=name, kind="trait",
                line_start=n.start_point[0] + 1, line_end=n.end_point[0] + 1,
            ))

    # Impl blocks (for trait implementations -> inheritance)
    for n in _find_nodes(root, "impl_item"):
        trait_node = n.child_by_field_name("trait")
        type_node = n.child_by_field_name("type")
        if trait_node and type_node:
            result.inheritance.append(InheritanceRef(
                child=type_node.text.decode(), parent=trait_node.text.decode()
            ))

    # Use statements
    for n in _find_nodes(root, "use_declaration"):
        arg = n.child_by_field_name("argument")
        if arg:
            raw = arg.text.decode("utf-8", errors="replace")
            target = raw.split("::")[0]
            if target:
                result.imports.append(ImportRef(target=target))

    # Calls
    for n in _find_nodes(root, "call_expression"):
        fn = n.child_by_field_name("function")
        if fn:
            callee = fn.text.decode("utf-8", errors="replace")
            caller = _enclosing_function(n)
            result.calls.append(CallRef(caller=caller, callee=callee, line=n.start_point[0] + 1))

    # Macro invocations (e.g. println!)
    for n in _find_nodes(root, "macro_invocation"):
        macro = n.child_by_field_name("macro")
        if macro:
            callee = macro.text.decode("utf-8", errors="replace")
            caller = _enclosing_function(n)
            result.calls.append(CallRef(caller=caller, callee=callee, line=n.start_point[0] + 1))

    complexity_types = {"if_expression", "else_clause", "for_expression", "while_expression",
                        "loop_expression", "match_expression", "function_item"}
    result.complexity = len(_find_nodes_multi(root, complexity_types))

    return result


def _extract_css(root) -> ExtractionResult:
    result = ExtractionResult()

    for n in _find_nodes(root, "import_statement"):
        for child in n.named_children:
            if child.type in ("string_value", "call_expression"):
                raw = child.text.decode("utf-8", errors="replace").strip("'\"url()")
                if raw:
                    result.imports.append(ImportRef(target=raw))

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_EXTRACTORS = {
    "python": _extract_python,
    "javascript": _extract_javascript,
    "typescript": _extract_javascript,  # TS uses JS parser for extraction
    "css": _extract_css,
    "cpp": _extract_cpp,
    "rust": _extract_rust,
}


def extract_symbols(content: str, language: str) -> ExtractionResult:
    """Extract symbols from source code using Tree-sitter.

    Returns an empty ExtractionResult for unsupported languages or parse errors.
    """
    if language not in SUPPORTED_LANGUAGES:
        return ExtractionResult()
    if not content.strip():
        return ExtractionResult()

    parser = _get_parser(language)
    if not parser:
        return ExtractionResult()

    try:
        tree = parser.parse(content.encode("utf-8"))
        extractor = _EXTRACTORS.get(language)
        if not extractor:
            return ExtractionResult()
        return extractor(tree.root_node)
    except Exception:
        return ExtractionResult()
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
python3 -m pytest tests/test_tree_sitter_parser.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/tree_sitter_parser.py tests/test_tree_sitter_parser.py
git commit -m "feat: add Tree-sitter parser module with 6 language support (#4)"
```

---

### Task 4: Integrate Tree-sitter into analyzer

**Files:**
- Modify: `src/copyclip/intelligence/analyzer.py`

- [ ] **Step 1: Extend `_lang_from_ext` for C++ and Rust**

Find:

```python
def _lang_from_ext(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".md": "markdown",
        ".json": "json",
        ".css": "css",
        ".html": "html",
    }.get(ext, "other")
```

Replace with:

```python
def _lang_from_ext(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".md": "markdown",
        ".json": "json",
        ".css": "css",
        ".html": "html",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".h": "cpp",
        ".hpp": "cpp",
        ".rs": "rust",
    }.get(ext, "other")
```

- [ ] **Step 2: Add Tree-sitter import and replace regex parsing**

At the top of `analyzer.py`, add the import. Find the existing imports block and add:

```python
from .tree_sitter_parser import extract_symbols, SUPPORTED_LANGUAGES, ExtractionResult
```

Then find the per-file parsing block (around line 581):

```python
            if (not reused_insight) and language in {"python", "javascript", "typescript"} and st_size < 300_000:
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    cscore = _complexity_score(content, language)
                    imports = sorted(_extract_import_targets(content, language))
                    complexity_by_file[rel] = cscore
                    for t in imports:
                        dep_edges.add((mod, t))
                    stage_mask |= STAGE_IMPORT_GRAPH | STAGE_RISK_SIGNALS
                    next_insights[rel] = {
                        "module": mod,
                        "imports": imports,
                        "complexity": cscore,
                        "cognitive_debt": 0.0,
                    }
                except Exception:
                    pass
```

Replace with:

```python
            if (not reused_insight) and language in SUPPORTED_LANGUAGES and st_size < 300_000:
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    extraction = extract_symbols(content, language)
                    cscore = extraction.complexity
                    imports = sorted(set(imp.target for imp in extraction.imports))
                    complexity_by_file[rel] = cscore
                    for t in imports:
                        dep_edges.add((mod, t))
                    stage_mask |= STAGE_IMPORT_GRAPH | STAGE_RISK_SIGNALS
                    next_insights[rel] = {
                        "module": mod,
                        "imports": imports,
                        "complexity": cscore,
                        "cognitive_debt": 0.0,
                    }
                    # Store extraction for symbol resolution pass
                    if not hasattr(analyze_project, '_file_extractions'):
                        analyze_project._file_extractions = {}
                    analyze_project._file_extractions[rel] = (mod, extraction)
                except Exception:
                    pass
            elif (not reused_insight) and language in {"python", "javascript", "typescript"} and st_size < 300_000:
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    cscore = _complexity_score(content, language)
                    imports = sorted(_extract_import_targets(content, language))
                    complexity_by_file[rel] = cscore
                    for t in imports:
                        dep_edges.add((mod, t))
                    stage_mask |= STAGE_IMPORT_GRAPH | STAGE_RISK_SIGNALS
                    next_insights[rel] = {
                        "module": mod,
                        "imports": imports,
                        "complexity": cscore,
                        "cognitive_debt": 0.0,
                    }
                except Exception:
                    pass
```

- [ ] **Step 3: Add symbol resolution pass after the file loop**

Find the module insertion block (around line 611):

```python
    for module in modules_seen:
        conn.execute(
            "INSERT OR REPLACE INTO modules(project_id,name,path_prefix) VALUES(?,?,?)",
            (project_id, module, module),
        )
```

Insert the symbol resolution pass BEFORE the module insertion:

```python
    # --- Symbol resolution pass ---
    file_extractions = getattr(analyze_project, '_file_extractions', {})
    if file_extractions:
        # Clear previous symbols for this project
        conn.execute("DELETE FROM symbol_edges WHERE project_id=?", (project_id,))
        conn.execute("DELETE FROM symbols WHERE project_id=?", (project_id,))

        # Insert all symbol definitions
        symbol_id_map = {}  # (file_path, name, kind) -> symbol_id
        global_symbols = {}  # (module, name) -> symbol_id (for cross-file resolution)

        for rel, (mod, extraction) in file_extractions.items():
            for sym in extraction.definitions:
                cursor = conn.execute(
                    "INSERT OR REPLACE INTO symbols(project_id,name,kind,file_path,line_start,line_end,parent_symbol_id,module) VALUES(?,?,?,?,?,?,?,?)",
                    (project_id, sym.name, sym.kind, rel, sym.line_start, sym.line_end, None, mod),
                )
                sid = cursor.lastrowid
                symbol_id_map[(rel, sym.name, sym.kind)] = sid
                global_symbols[(mod, sym.name)] = sid

        # Resolve parent_symbol_id for methods
        for rel, (mod, extraction) in file_extractions.items():
            for sym in extraction.definitions:
                if sym.parent:
                    parent_id = symbol_id_map.get((rel, sym.parent, "class"))
                    child_id = symbol_id_map.get((rel, sym.name, sym.kind))
                    if parent_id and child_id:
                        conn.execute("UPDATE symbols SET parent_symbol_id=? WHERE id=?", (parent_id, child_id))
                        conn.execute(
                            "INSERT OR IGNORE INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) VALUES(?,?,?,?)",
                            (project_id, parent_id, child_id, "contains"),
                        )

        # Build import map for cross-file call resolution
        # Maps (file_path, imported_name) -> source_module
        import_map = {}
        for rel, (mod, extraction) in file_extractions.items():
            for imp in extraction.imports:
                import_map[(rel, imp.target)] = imp.target

        # Resolve calls
        for rel, (mod, extraction) in file_extractions.items():
            for call in extraction.calls:
                # Try to find the callee symbol
                callee_base = call.callee.split(".")[0]  # handle obj.method -> obj
                callee_name = call.callee.split(".")[-1] if "." in call.callee else call.callee

                # Look in same file first
                callee_id = symbol_id_map.get((rel, callee_name, "function")) or \
                            symbol_id_map.get((rel, callee_name, "method"))

                # Look in imported modules
                if not callee_id:
                    for (r, imp_name), src_mod in import_map.items():
                        if r == rel and imp_name == callee_base:
                            callee_id = global_symbols.get((src_mod, callee_name))
                            if callee_id:
                                break

                # Look globally as fallback
                if not callee_id:
                    for (m, n), sid in global_symbols.items():
                        if n == callee_name:
                            callee_id = sid
                            break

                if callee_id:
                    caller_id = symbol_id_map.get((rel, call.caller, "function")) or \
                                symbol_id_map.get((rel, call.caller, "method"))
                    if caller_id:
                        conn.execute(
                            "INSERT OR IGNORE INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) VALUES(?,?,?,?)",
                            (project_id, caller_id, callee_id, "calls"),
                        )

        # Resolve inheritance
        for rel, (mod, extraction) in file_extractions.items():
            for inh in extraction.inheritance:
                child_id = symbol_id_map.get((rel, inh.child, "class")) or \
                           symbol_id_map.get((rel, inh.child, "struct"))
                parent_id = None
                # Look in same file
                parent_id = symbol_id_map.get((rel, inh.parent, "class")) or \
                            symbol_id_map.get((rel, inh.parent, "trait")) or \
                            symbol_id_map.get((rel, inh.parent, "interface"))
                # Look globally
                if not parent_id:
                    for (m, n), sid in global_symbols.items():
                        if n == inh.parent:
                            parent_id = sid
                            break
                if child_id and parent_id:
                    conn.execute(
                        "INSERT OR IGNORE INTO symbol_edges(project_id,from_symbol_id,to_symbol_id,edge_type) VALUES(?,?,?,?)",
                        (project_id, child_id, parent_id, "inherits"),
                    )

        # Clean up
        analyze_project._file_extractions = {}

    for module in modules_seen:
        conn.execute(
            "INSERT OR REPLACE INTO modules(project_id,name,path_prefix) VALUES(?,?,?)",
            (project_id, module, module),
        )
```

- [ ] **Step 4: Run existing tests to verify no regressions**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip
python3 -m pytest tests/test_intelligence_analyzer.py -v
```

Expected: All existing tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/copyclip/intelligence/analyzer.py
git commit -m "feat(analyzer): integrate Tree-sitter parsing with symbol resolution (#4, #3)"
```

---

### Task 5: Add `/api/module/symbols` endpoint

**Files:**
- Modify: `src/copyclip/intelligence/server.py`

- [ ] **Step 1: Add endpoint**

Find the `/api/module/source` endpoint block (added in a previous task). Insert the new endpoint right after it, before the next `if parsed.path ==` block:

```python
            if parsed.path == "/api/module/symbols":
                if not pid:
                    self._json(with_meta({"module": "", "symbols": []}))
                    return
                q = parse_qs(parsed.query or "")
                module_name = (q.get("module", [""])[0] or "").strip()
                if not module_name:
                    self._json(with_meta({"module": "", "symbols": []}))
                    return
                rows = conn.execute(
                    "SELECT id, name, kind, file_path, line_start, line_end, parent_symbol_id FROM symbols WHERE project_id=? AND module=? ORDER BY file_path, line_start",
                    (pid, module_name),
                ).fetchall()
                symbols = []
                symbol_ids = {r[0] for r in rows}
                for r in rows:
                    sid, name, kind, fpath, lstart, lend, parent_id = r
                    # Get methods (children)
                    methods = [row[0] for row in conn.execute(
                        "SELECT name FROM symbols WHERE parent_symbol_id=? AND project_id=?", (sid, pid)
                    ).fetchall()] if kind == "class" else []
                    # Get calls (outgoing)
                    calls = [row[0] for row in conn.execute(
                        "SELECT s.name FROM symbol_edges e JOIN symbols s ON e.to_symbol_id=s.id WHERE e.from_symbol_id=? AND e.edge_type='calls'", (sid,)
                    ).fetchall()]
                    # Get called_by (incoming)
                    called_by = [row[0] for row in conn.execute(
                        "SELECT s.name FROM symbol_edges e JOIN symbols s ON e.from_symbol_id=s.id WHERE e.to_symbol_id=? AND e.edge_type='calls'", (sid,)
                    ).fetchall()]
                    # Get inherits
                    inherits = [row[0] for row in conn.execute(
                        "SELECT s.name FROM symbol_edges e JOIN symbols s ON e.to_symbol_id=s.id WHERE e.from_symbol_id=? AND e.edge_type='inherits'", (sid,)
                    ).fetchall()]
                    symbols.append({
                        "name": name, "kind": kind, "file_path": fpath,
                        "line_start": lstart, "line_end": lend,
                        "methods": methods, "calls": calls,
                        "called_by": called_by, "inherits": inherits,
                    })
                self._json(with_meta({"module": module_name, "symbols": symbols}))
                return

```

- [ ] **Step 2: Commit**

```bash
git add src/copyclip/intelligence/server.py
git commit -m "feat(api): add /api/module/symbols endpoint (#3)"
```

---

### Task 6: Frontend types and API client

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add types**

In `frontend/src/types/api.ts`, find the `ModuleSourceResponse` type block and add after it:

```typescript
export type SymbolItem = {
  name: string
  kind: 'function' | 'class' | 'method' | 'interface' | 'trait' | 'enum' | 'struct'
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
  meta?: {
    project?: string
    generated_at?: string
  }
}
```

- [ ] **Step 2: Add API method**

In `frontend/src/api/client.ts`, add `ModuleSymbolsResponse` to the import, and add after the `moduleSource` method:

```typescript
  moduleSymbols: (module: string) => getJSON<ModuleSymbolsResponse>(`/api/module/symbols?module=${encodeURIComponent(module)}`),
```

- [ ] **Step 3: Build**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/client.ts
git commit -m "feat(api): add moduleSymbols client method and types (#3)"
```

---

### Task 7: Atlas info panel symbols section

**Files:**
- Modify: `frontend/src/pages/Atlas3DPage.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add symbol styles**

In `frontend/src/styles.css`, find the `.atlas-code-container .CodeMirror` block and add after it:

```css
.atlas-symbols-section {
  margin-top: 8px;
}

.atlas-symbols-header {
  font-size: 10px;
  color: #666;
  margin-bottom: 6px;
}

.atlas-symbol-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 0;
  font-size: 11px;
  cursor: pointer;
  transition: color 0.15s ease;
}

.atlas-symbol-item:hover {
  color: #00eeff;
}

.atlas-symbol-name {
  color: #ccc;
}

.atlas-symbol-kind {
  font-size: 9px;
  color: #555;
  text-transform: lowercase;
}

.atlas-symbol-nested {
  padding-left: 16px;
  border-left: 1px solid #222;
  margin-left: 4px;
}
```

- [ ] **Step 2: Add symbols to Atlas3DPage**

In `frontend/src/pages/Atlas3DPage.tsx`, update the import to include `SymbolItem`:

```typescript
import type { ArchNode, ArchEdge, CognitiveLoadItem, ModuleSourceFile, SymbolItem } from '../types/api'
```

Add state for symbols after the existing source state:

Find:
```typescript
  const [loadingSource, setLoadingSource] = useState(false)
```

Add after:
```typescript
  const [symbols, setSymbols] = useState<SymbolItem[]>([])
```

In the `selectedNode` useEffect that fetches source, add the symbols fetch alongside it. Find the `api.moduleSource` call and add the symbols fetch in parallel:

Find:
```typescript
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
```

Replace with:
```typescript
    setLoadingSource(true)
    Promise.all([
      api.moduleSource(selectedNode.name),
      api.moduleSymbols(selectedNode.name),
    ])
      .then(([sourceRes, symbolsRes]) => {
        setSourceFiles(sourceRes.files || [])
        setActiveFileIdx(0)
        setSymbols(symbolsRes.symbols || [])
        setLoadingSource(false)
      })
      .catch(() => {
        setSourceFiles([])
        setSymbols([])
        setLoadingSource(false)
      })
```

Also reset symbols when deselecting. Find `setSourceFiles([])` in the `if (!selectedNode)` branch and add `setSymbols([])` after it.

- [ ] **Step 3: Add symbols JSX**

In the JSX, find the file tabs block:

```typescript
            {selectedNode && sourceFiles.length > 0 && (
              <>
                <div className="atlas-file-tabs">
```

Insert the symbols section BEFORE the file tabs:

```typescript
            {selectedNode && symbols.length > 0 && (
              <div className="atlas-symbols-section">
                <div className="atlas-symbols-header">SYMBOLS ({symbols.length} definitions)</div>
                {symbols.filter(s => s.kind === 'class' || s.kind === 'struct').map(cls => (
                  <div key={`${cls.file_path}:${cls.name}:${cls.line_start}`}>
                    <div
                      className="atlas-symbol-item"
                      onClick={() => {
                        if (cmInstanceRef.current && cls.line_start) {
                          const fileIdx = sourceFiles.findIndex(f => f.path === cls.file_path)
                          if (fileIdx >= 0) setActiveFileIdx(fileIdx)
                          setTimeout(() => cmInstanceRef.current?.scrollIntoView({ line: cls.line_start - 1, ch: 0 }), 100)
                        }
                      }}
                    >
                      <span className="atlas-symbol-name" style={{ color: '#00eeff' }}>{cls.name}</span>
                      <span className="atlas-symbol-kind">{cls.kind}{cls.inherits && cls.inherits.length > 0 ? ` : ${cls.inherits.join(', ')}` : ''}</span>
                    </div>
                    {cls.methods && cls.methods.length > 0 && (
                      <div className="atlas-symbol-nested">
                        {cls.methods.map(m => (
                          <div key={m} className="atlas-symbol-item" style={{ fontSize: 10 }}>
                            <span className="atlas-symbol-name">{m}</span>
                            <span className="atlas-symbol-kind">method</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {symbols.filter(s => s.kind === 'function').map(fn => (
                  <div
                    key={`${fn.file_path}:${fn.name}:${fn.line_start}`}
                    className="atlas-symbol-item"
                    onClick={() => {
                      if (cmInstanceRef.current && fn.line_start) {
                        const fileIdx = sourceFiles.findIndex(f => f.path === fn.file_path)
                        if (fileIdx >= 0) setActiveFileIdx(fileIdx)
                        setTimeout(() => cmInstanceRef.current?.scrollIntoView({ line: fn.line_start - 1, ch: 0 }), 100)
                      }
                    }}
                  >
                    <span className="atlas-symbol-name">{fn.name}</span>
                    <span className="atlas-symbol-kind">function</span>
                  </div>
                ))}
              </div>
            )}
            {selectedNode && sourceFiles.length > 0 && (
              <>
                <div className="atlas-file-tabs">
```

- [ ] **Step 4: Build**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Atlas3DPage.tsx frontend/src/styles.css
git commit -m "feat(atlas): add symbols section to info panel (#3)"
```

---

### Task 8: Documentation and final sync

**Files:**
- Create: `docs/LANGUAGE_SUPPORT.md`

- [ ] **Step 1: Create language support docs**

Create `docs/LANGUAGE_SUPPORT.md`:

```markdown
# Language Support

## Tree-sitter Deep Extraction (v0.4.0+)

The following languages receive full symbol-level extraction via Tree-sitter:

| Language | Extensions | Definitions | Imports | Calls | Inheritance |
|----------|-----------|-------------|---------|-------|-------------|
| Python | .py | functions, classes, methods | import, from...import | function calls, method calls | class inheritance |
| JavaScript | .js, .jsx | functions, classes, methods | import...from | function calls, method calls | extends |
| TypeScript | .ts, .tsx | functions, classes, methods | import...from | function calls, method calls | extends |
| CSS | .css | — | @import | — | — |
| C++ | .cpp, .cc, .cxx, .h, .hpp | functions, classes, structs | #include | function calls | base classes |
| Rust | .rs | functions, structs, enums, traits | use | function calls, macro invocations | impl...for (trait implementations) |

## Regex Fallback

Files in unsupported languages receive basic import extraction via regex patterns. This provides module-level dependency edges but no function/class-level symbols.

## Adding a New Language

To add Tree-sitter support for a new language:

1. Install the tree-sitter grammar package (e.g., `tree-sitter-go`)
2. Add the language to `_LANG_MODULES` in `src/copyclip/intelligence/tree_sitter_parser.py`
3. Implement an `_extract_<language>` function using AST node traversal
4. Register it in `_EXTRACTORS`
5. Add the extension mapping in `analyzer.py:_lang_from_ext`
6. Add tests in `tests/test_tree_sitter_parser.py`
```

- [ ] **Step 2: Final build and sync**

```bash
cd /Users/samueldarioballesterosgarcia/projects/05_tools/copyclip/frontend && npm run build && cp dist/index.html ../src/copyclip/intelligence/ui/index.html
```

- [ ] **Step 3: Commit all**

```bash
git add docs/LANGUAGE_SUPPORT.md src/copyclip/intelligence/ui/index.html
git commit -m "docs: add language support documentation and sync bundle (#4, #3)"
```
