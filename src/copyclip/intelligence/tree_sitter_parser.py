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
