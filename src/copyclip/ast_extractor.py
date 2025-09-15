from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

_SECRET_PAT = re.compile(
    r"(AKIA[0-9A-Z]{16}|"
    r"ASIA[0-9A-Z]{16}|"
    r"AIza[0-9A-Za-z\-_]{35}|"
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----|"
    r"password\s*=\s*['\"].+?['\"]|"
    r"secret[_-]?key\s*=\s*['\"].+?['\"])",
    re.IGNORECASE,
)

# Brief: _redact
def _redact(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    return _SECRET_PAT.sub("[REDACTED]", s)

@dataclass(frozen=True)
# Brief: ContextRecord
class ContextRecord:
    module_name: str
    symbol_path: str  # e.g. "pkg.mod:Class.method" or "pkg.mod:func"
    kind: str         # module|class|function|method
    name: str
    signature_text: str
    visibility: str   # public|private
    decorators: Tuple[str, ...] = field(default_factory=tuple)
    is_async: bool = False
    called_names: Tuple[str, ...] = field(default_factory=tuple)
    referenced_names: Tuple[str, ...] = field(default_factory=tuple)
    raise_names: Tuple[str, ...] = field(default_factory=tuple)
    existing_firstline: str = ""
    lineno: int = 0
    # Enhanced fields for richer docstring generation / analysis
    # param_types: ("name: annotation") entries (annotation as source text or "Any")
    param_types: Tuple[str, ...] = field(default_factory=tuple)
    # return_annotation: textual return annotation (or empty string)
    return_annotation: str = ""
    # Detected side-effects like "file I/O", "network I/O", "console output", etc.
    side_effects: Tuple[str, ...] = field(default_factory=tuple)

@dataclass(frozen=True)
# Brief: ModuleContext
class ModuleContext:
    module_name: str
    public_symbol_names: Tuple[str, ...]
    inferred_responsibilities: Tuple[str, ...]
    external_dependencies: Tuple[str, ...]
    file_sha256: str

# Brief: _module_name_from_path
def _module_name_from_path(path: Optional[str]) -> str:
    if not path:
        return "__main__"
    path = path.replace(os.sep, "/")
    base = os.path.splitext(os.path.basename(path))[0]
    return base or "__main__"

# Brief: _sha256
def _sha256(text: str) -> str:
    import hashlib as _h
    return _h.sha256(text.encode("utf-8")).hexdigest()

# Brief: _sig_from_ast_func
def _sig_from_ast_func(node: ast.AST) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    args = node.args
    parts: List[str] = []
    def _fmt_arg(a: ast.arg, default: Optional[ast.expr] = None, annotation: Optional[ast.expr] = None) -> str:
        name = a.arg
        ann = ""
        if a.annotation:
            try:
                ann = f": {ast.unparse(a.annotation)}"
            except Exception:
                ann = ""
        elif annotation:
            try:
                ann = f": {ast.unparse(annotation)}"
            except Exception:
                ann = ""
        if default is not None:
            return f"{name}{ann}=..."
        return f"{name}{ann}"

    for i, a in enumerate(getattr(args, "posonlyargs", [])):  # py3.8+
        parts.append(_fmt_arg(a, None))

    for i, a in enumerate(args.args):
        default = None
        if args.defaults:
            di = i - (len(args.args) - len(args.defaults))
            if di >= 0:
                default = args.defaults[di]
        parts.append(_fmt_arg(a, default))

    if args.vararg:
        parts.append("*" + args.vararg.arg)

    if getattr(args, "kwonlyargs", []):
        if not args.vararg:
            parts.append("*")
        for i, a in enumerate(args.kwonlyargs):
            default = None
            if args.kw_defaults and args.kw_defaults[i] is not None:
                default = args.kw_defaults[i]
            parts.append(_fmt_arg(a, default))

    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    ret = ""
    if node.returns:
        try:
            ret = f" -> {ast.unparse(node.returns)}"
        except Exception:
            ret = ""
    return f"{node.name}(" + ", ".join(parts) + ")" + f"{ret}"

# Brief: _expr_to_src
def _expr_to_src(e: ast.AST) -> str:
    try:
        return ast.unparse(e)  # py3.9+
    except Exception:
        if isinstance(e, ast.Name):
            return e.id
        return "Any"

# Brief: _collect_names_in_body
def _collect_names_in_body(body: List[ast.stmt]) -> Tuple[Set[str], Set[str], Set[str]]:
    """
    
        Walk a list of statements and collect:
          - calls: dotted names where possible (e.g. "os.path.join", "requests.get")
          - refs: referenced names/imports/constants
          - raises: exception constructor/names
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    calls: Set[str] = set()
    refs: Set[str] = set()
    raises: Set[str] = set()

    def _get_full_name(node: ast.AST) -> str:
        # Try to reconstruct dotted name from Attribute/Name nodes.
        if isinstance(node, ast.Name):
            return node.id
        parts: List[str] = []
        cur = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return ".".join(reversed(parts))
        return ""

    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            name = _get_full_name(node.func)
            if name:
                calls.add(name)
            # Continue descent to find nested calls/refs
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name):
            refs.add(node.id)

        def visit_Attribute(self, node: ast.Attribute):
            # Add the attribute name and attempt to capture dotted chain via parent node in visit_Call
            refs.add(node.attr)
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import):
            for n in node.names:
                refs.add(n.name.split(".")[0])

        def visit_ImportFrom(self, node: ast.ImportFrom):
            if node.module:
                refs.add(node.module.split(".")[0])
            for n in node.names:
                refs.add(n.name)

        def visit_Raise(self, node: ast.Raise):
            if node.exc:
                if isinstance(node.exc, ast.Name):
                    raises.add(node.exc.id)
                elif isinstance(node.exc, ast.Call):
                    nm = _get_full_name(node.exc.func)
                    if nm:
                        raises.add(nm)
                    elif isinstance(node.exc.func, ast.Name):
                        raises.add(node.exc.func.id)
            self.generic_visit(node)

    V().visit(ast.Module(body=body, type_ignores=[]))
    return calls, refs, raises

# Brief: _decorator_names
def _decorator_names(node: ast.AST) -> Tuple[str, ...]:
    decos: List[str] = []
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        for d in node.decorator_list:
            if isinstance(d, ast.Name):
                decos.append(d.id)
            elif isinstance(d, ast.Attribute):
                decos.append(d.attr)
            else:
                decos.append("decorator")
    return tuple(decos)

# --- Dependency graph (relative imports) --------------------------------------
def _sanitize_id(label: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", label)

# Brief: _module_name_from_relpath
def _module_name_from_relpath(relpath: str) -> str:
    relpath = relpath.replace(os.sep, "/")
    if relpath.endswith(".py"):
        relpath = relpath[:-3]
    return relpath.replace("/", ".")

# Brief: _resolve_relative_import
def _resolve_relative_import(curr_mod: str, level: int, module: Optional[str], imported_name: Optional[str]) -> Optional[str]:
    # curr_mod like "pkg.sub.module"
    parts = curr_mod.split(".")
    if level > len(parts):
        return None
    base = parts[: len(parts) - level]
    if module:
        target_parts = base + module.split(".")
    elif imported_name:
        target_parts = base + [imported_name]
    else:
        return None
    return ".".join([p for p in target_parts if p])

# Brief: build_dependency_mermaid
def build_dependency_mermaid(files: Dict[str, str]) -> str:
    """
    Build Mermaid graph (graph TD;) using only relative imports (Python).
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    edges: Set[Tuple[str, str]] = set()
    nodes: Set[str] = set()

    for rel_path, content in files.items():
        if not rel_path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content or "")
        except Exception:
            continue
        curr_mod = _module_name_from_relpath(rel_path)
        nodes.add(curr_mod)

        for n in tree.body:
            # Only relative imports: from .foo import bar / from . import reader
            if isinstance(n, ast.ImportFrom) and getattr(n, "level", 0) > 0:
                if n.names:
                    for alias in n.names:
                        tgt = _resolve_relative_import(curr_mod, n.level, n.module, alias.name)
                        if tgt:
                            nodes.add(tgt)
                            edges.add((curr_mod, tgt))
                else:
                    # Very rare: "from . import" without names – ignore
                    ...

    if not nodes:
        return ""

    # Build Mermaid with stable ids and human labels
    id_for = {name: _sanitize_id(name) for name in sorted(nodes)}
    lines = ["graph TD;"]
    for name, nid in id_for.items():
        lines.append(f'    {nid}["{name}"];')
    for a, b in sorted(edges):
        lines.append(f"    {id_for[a]} --> {id_for[b]};")
    return "\n".join(lines)

# Brief: extract_python_context
def extract_python_context(content: str, *, module_path: Optional[str] = None) -> Tuple[ModuleContext, List[ContextRecord]]:
    tree = ast.parse(content or "")
    module_name = _module_name_from_path(module_path)
    body = list(tree.body)

    pub: List[str] = []
    ext_deps: Set[str] = set()
    responsibilities: Set[str] = set()

    for n in body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            if isinstance(n, ast.Import):
                for nn in n.names:
                    ext_deps.add(nn.name.split(".")[0])
            else:
                if n.module:
                    ext_deps.add(n.module.split(".")[0])

    def _existing_firstline(n: ast.AST) -> str:
        ds = ast.get_docstring(n, clean=True) or ""
        return ds.splitlines()[0] if ds else ""

    records: List[ContextRecord] = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.cls_stack: List[str] = []

        def _add_func(self, node: ast.AST, is_async: bool):
            assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            name = node.name
            kind = "method" if self.cls_stack else "function"
            sym_path = f"{module_name}:{'.'.join(self.cls_stack + [name])}"
            sig = f"def {_sig_from_ast_func(node)}:"
            calls, refs, raises = _collect_names_in_body(node.body)

            # Parameter types extraction (best-effort)
            param_types: List[str] = []
            try:
                args = getattr(node, "args")
                for a in getattr(args, "posonlyargs", []):
                    ann = ""
                    try:
                        ann = ast.unparse(a.annotation) if getattr(a, "annotation", None) is not None else ""
                    except Exception:
                        ann = ""
                    param_types.append(f"{a.arg}: {ann or 'Any'}")
                for a in getattr(args, "args", []):
                    ann = ""
                    try:
                        ann = ast.unparse(a.annotation) if getattr(a, "annotation", None) is not None else ""
                    except Exception:
                        ann = ""
                    param_types.append(f"{a.arg}: {ann or 'Any'}")
                if getattr(args, "vararg", None):
                    v = args.vararg
                    ann = ""
                    try:
                        ann = ast.unparse(v.annotation) if getattr(v, "annotation", None) is not None else ""
                    except Exception:
                        ann = ""
                    param_types.append(f"*{v.arg}: {ann or 'Any'}")
                for a in getattr(args, "kwonlyargs", []):
                    ann = ""
                    try:
                        ann = ast.unparse(a.annotation) if getattr(a, "annotation", None) is not None else ""
                    except Exception:
                        ann = ""
                    param_types.append(f"{a.arg}: {ann or 'Any'}")
                if getattr(args, "kwarg", None):
                    k = args.kwarg
                    ann = ""
                    try:
                        ann = ast.unparse(k.annotation) if getattr(k, "annotation", None) is not None else ""
                    except Exception:
                        ann = ""
                    param_types.append(f"**{k.arg}: {ann or 'Any'}")
            except Exception:
                param_types = []

            # Return annotation (best-effort)
            return_ann = ""
            try:
                if getattr(node, "returns", None) is not None:
                    return_ann = ast.unparse(node.returns)
            except Exception:
                return_ann = ""

            # Side-effects heuristics based on called names
            side_effects_set: Set[str] = set()
            for cname in calls:
                lname = cname.lower()
                last = lname.split(".")[-1]
                if last in ("open", "read", "write", "write_text", "read_text"):
                    side_effects_set.add("file I/O")
                if lname.startswith("requests.") or lname.startswith("httpx.") or "requests" in lname or "httpx" in lname:
                    side_effects_set.add("network I/O")
                if lname.startswith("subprocess.") or last in ("popen", "run", "call", "check_output"):
                    side_effects_set.add("process")
                if last in ("print",):
                    side_effects_set.add("console output")
                if lname.startswith("os.") or lname.startswith("shutil.") or last in ("remove", "rename", "copy"):
                    side_effects_set.add("filesystem")

            rec = ContextRecord(
                module_name=module_name,
                symbol_path=sym_path,
                kind=kind,
                name=name,
                signature_text=sig,
                visibility="private" if name.startswith("_") else "public",
                decorators=_decorator_names(node),
                is_async=is_async,
                called_names=tuple(sorted(calls)),
                referenced_names=tuple(sorted(refs)),
                raise_names=tuple(sorted(raises)),
                existing_firstline=_existing_firstline(node),
                lineno=getattr(node, "lineno", 0),
                param_types=tuple(param_types),
                return_annotation=return_ann or "",
                side_effects=tuple(sorted(side_effects_set)),
            )
            records.append(rec)
            if not name.startswith("_"):
                pub.append(name)
            if calls:
                responsibilities.add("orchestrates calls")
            if raises:
                responsibilities.add("error handling")
            if refs:
                responsibilities.add("uses imports/constants")

        def visit_FunctionDef(self, node: ast.FunctionDef):
            self._add_func(node, False)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self._add_func(node, True)

        def visit_ClassDef(self, node: ast.ClassDef):
            name = node.name
            sym_path = f"{module_name}:{'.'.join(self.cls_stack + [name])}"
            calls, refs, raises = _collect_names_in_body(node.body)

            # Simple side-effects detection for classes (based on body calls)
            side_effects_set: Set[str] = set()
            for cname in calls:
                lname = cname.lower()
                last = lname.split(".")[-1]
                if last in ("open", "read", "write", "write_text", "read_text"):
                    side_effects_set.add("file I/O")
                if lname.startswith("requests.") or lname.startswith("httpx."):
                    side_effects_set.add("network I/O")
                if lname.startswith("subprocess.") or last in ("popen", "run", "call", "check_output"):
                    side_effects_set.add("process")
                if last in ("print",):
                    side_effects_set.add("console output")
                if lname.startswith("os.") or lname.startswith("shutil.") or last in ("remove", "rename", "copy"):
                    side_effects_set.add("filesystem")

            rec = ContextRecord(
                module_name=module_name,
                symbol_path=sym_path,
                kind="class",
                name=name,
                signature_text=f"class {name}:",
                visibility="private" if name.startswith("_") else "public",
                decorators=_decorator_names(node),
                is_async=False,
                called_names=tuple(sorted(calls)),
                referenced_names=tuple(sorted(refs)),
                raise_names=tuple(sorted(raises)),
                existing_firstline=_existing_firstline(node),
                lineno=getattr(node, "lineno", 0),
                param_types=tuple(),
                return_annotation="",
                side_effects=tuple(sorted(side_effects_set)),
            )
            records.append(rec)
            if not name.startswith("_"):
                pub.append(name)
            self.cls_stack.append(name)
            self.generic_visit(node)
            self.cls_stack.pop()

    V().visit(tree)

    mod_ctx = ModuleContext(
        module_name=module_name,
        public_symbol_names=tuple(sorted(set(pub))),
        inferred_responsibilities=tuple(sorted(responsibilities)) or tuple(),
        external_dependencies=tuple(sorted(ext_deps)),
        file_sha256=_sha256(content),
    )

    out: List[ContextRecord] = []
    for r in records:
        out.append(
            ContextRecord(
                module_name=r.module_name,
                symbol_path=r.symbol_path,
                kind=r.kind,
                name=r.name,
                signature_text=_redact(r.signature_text) or "",
                visibility=r.visibility,
                decorators=r.decorators,
                is_async=r.is_async,
                called_names=r.called_names,
                referenced_names=tuple(_redact(x) or "" for x in r.referenced_names),
                raise_names=r.raise_names,
                existing_firstline=_redact(r.existing_firstline) or "",
                lineno=r.lineno,
                param_types=tuple(_redact(x) or "" for x in getattr(r, "param_types", ())),
                return_annotation=_redact(getattr(r, "return_annotation", "")) or "",
                side_effects=tuple(getattr(r, "side_effects", ())),
            )
        )
    out.sort(key=lambda x: x.lineno)
    return mod_ctx, out

# -------------------- JS/TS structural extractor --------------------------------

_JS_DECL = re.compile(
    r"""
    (?P<func>^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<fname>[A-Za-z_$][A-Za-z0-9_$]*)\s*\()|
    (?P<class>^\s*(?:export\s+)?class\s+(?P<cname>[A-Za-z_$][A-Za-z0-9_$]*)\b)|
    (?P<arrow>^\s*(?:const|let|var)\s+(?P<aname>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)
    """,
    re.VERBOSE | re.MULTILINE,
)

_JS_IMPORT_REL = re.compile(
    r"""^\s*import\s+(?:.+?\s+from\s+)?["'](?P<path>\.[^"']+)["']|require\(\s*["'](?P<rpath>\.[^"']+)["']\s*\)""",
    re.MULTILINE,
)

# Brief: extract_jsts_context
def extract_jsts_context(content: str, *, module_path: Optional[str] = None) -> Tuple[ModuleContext, List[ContextRecord]]:
    module_name = _module_name_from_path(module_path)
    records: List[ContextRecord] = []
    pub: List[str] = []
    ext_deps: Set[str] = set()
    responsibilities: Set[str] = set()

    for m in re.finditer(r"^\s*import\s+(?P<what>.+?)\s+from\s+['\"](?P<pkg>[^'\"]+)['\"]", content, re.MULTILINE):
        pkg = m.group("pkg")
        if not pkg.startswith("."):
            ext_deps.add(pkg.split("/")[0])

    for match in _JS_DECL.finditer(content):
        fname = match.group("fname")
        cname = match.group("cname")
        aname = match.group("aname")
        is_func = bool(fname or aname)
        name = fname or cname or aname or "anonymous"
        kind = "class" if cname else "function"
        is_async = bool(match.group("func")) or bool(match.group("arrow"))
        sig = f"{'async ' if is_async else ''}{'class' if kind=='class' else 'function'} {name}(...)"
        sym_path = f"{module_name}:{name}"
        rec = ContextRecord(
            module_name=module_name,
            symbol_path=sym_path,
            kind=kind,
            name=name,
            signature_text=sig,
            visibility="private" if name.startswith("_") else "public",
            decorators=tuple(),
            is_async=is_async,
            called_names=tuple(),
            referenced_names=tuple(),
            raise_names=tuple(),
            existing_firstline="",
            lineno=content.count("\n", 0, match.start()) + 1,
        )
        records.append(rec)
        if not name.startswith("_"):
            pub.append(name)

    mod_ctx = ModuleContext(
        module_name=module_name,
        public_symbol_names=tuple(sorted(set(pub))),
        inferred_responsibilities=tuple(sorted(responsibilities)) or tuple(),
        external_dependencies=tuple(sorted(ext_deps)),
        file_sha256=_sha256(content),
    )
    records.sort(key=lambda r: r.lineno)
    return mod_ctx, records

# Brief: js_ts_collect_local_symbols
def js_ts_collect_local_symbols(content: str) -> Set[str]:
    syms: Set[str] = set()
    for m in _JS_DECL.finditer(content):
        if m.group("fname"):
            syms.add(m.group("fname"))
        if m.group("cname"):
            syms.add(m.group("cname"))
        if m.group("aname"):
            syms.add(m.group("aname"))
    return syms

# ---------------- Dependency graph (Python relative + JS/TS relative) -----------

# Brief: _resolve_py_relative
def _resolve_py_relative(from_rel_path: str, level: int, module: Optional[str], project_files: Set[str]) -> Optional[str]:
    """
    
        Resolve 'from .x import y' style to a module-like path string without extension.
        from_rel_path: 'pkg/mod.py'
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    base_dir = os.path.dirname(from_rel_path).replace("\\", "/")
    parts = base_dir.split("/") if base_dir else []
    # move up 'level' packages
    up = max(level, 0)
    if up > 0:
        parts = parts[:-up] if up <= len(parts) else []
    if module:
        parts += module.split(".")
    # Try to match an existing file:
    candidate_file = "/".join(parts) + ".py"
    candidate_init = "/".join(parts) + "/__init__.py"
    if candidate_file in project_files:
        return "/".join(parts)
    if candidate_init in project_files:
        return "/".join(parts)
    # best-effort: return joined even if not found
    return "/".join(parts) if parts else None

# Brief: _python_relative_edges
def _python_relative_edges(rel_path: str, content: str, project_files: Set[str]) -> List[Tuple[str, str]]:
    edges: List[Tuple[str, str]] = []
    try:
        tree = ast.parse(content or "")
    except Exception:
        return edges
    this_mod = rel_path.rsplit(".", 1)[0]
    for n in tree.body:
        if isinstance(n, ast.ImportFrom) and (n.level or 0) > 0:
            target = _resolve_py_relative(rel_path, n.level or 0, n.module, project_files)
            if target:
                edges.append((this_mod, target))
    return edges

# Brief: _js_relative_edges
def _js_relative_edges(rel_path: str, content: str) -> List[Tuple[str, str]]:
    edges: List[Tuple[str, str]] = []
    this_mod = rel_path.rsplit(".", 1)[0]
    for m in _JS_IMPORT_REL.finditer(content):
        raw = m.group("path") or m.group("rpath") or ""
        target = raw
        if target.endswith((".js", ".ts", ".tsx", ".mjs", ".cjs")):
            target = target.rsplit(".", 1)[0]
        # normalize './' '../' relative to 'this_mod'
        base_dir = os.path.dirname(this_mod)
        norm = os.path.normpath(os.path.join(base_dir, target)).replace("\\", "/")
        edges.append((this_mod, norm))
    return edges


