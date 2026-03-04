# src/copyclip/minimizer.py
from __future__ import annotations

import ast
import os
import re
import asyncio
import threading
import queue
import sys
from typing import Dict, List, Optional, Tuple, Set
import time

import logging
import json
from .llm_client import map_exception_to_log_data

from .llm_client import LLMClientFactory
from .llm.config import load_config, resolve_settings, pretty_settings
from .llm.minimizer_service import contextual_minimize
from .docstrings import generate_docstrings_for_file, _firstline
from .ast_extractor import (
    extract_python_context,
    extract_jsts_context,
    js_ts_collect_local_symbols,
    build_dependency_mermaid,  # exported for CLI use (optional)
)

MINIMIZATION_RULES: Dict[str, Dict[str, re.Pattern]] = {
    "python": {
        "comments": re.compile(r"(?m)^\s*#.*?$"),
        "docstrings": re.compile(r'(?s)(?:^[ \t]*("""|\'\'\')(?:.|\n)*?\1[ \t]*\n)'),
    },
    "javascript": {
        "comments": re.compile(r"(?s)//.*?$|/\*.*?\*/", re.M),
    },
    "typescript": {
        "comments": re.compile(r"(?s)//.*?$|/\*.*?\*/", re.M),
    },
    "css": {
        "comments": re.compile(r"(?s)/\*.*?\*/"),
    },
    "html": {
        "html_comments": re.compile(r"(?s)<!--.*?-->"),
    },
    "markdown": {
        "html_comments": re.compile(r"(?s)<!--.*?-->"),
    },
    "yaml": {
        "comments": re.compile(r"(?m)^\s*#.*?$"),
    },
    "toml": {
        "comments": re.compile(r"(?m)^\s*#.*?$"),
    },
}

# -----------------------------------------------------------------------------
# Lightweight progress + debug logging
# -----------------------------------------------------------------------------
_DEBUG = os.getenv("COPYCLIP_DEBUG", "0").lower() not in ("0", "false", "")
_PROGRESS = os.getenv("COPYCLIP_PROGRESS", "1").lower() not in ("0", "false", "")
_LOG_ONCE_KEYS: Set[str] = set()
_PROMPT_CACHE: Dict[str, Optional[str]] = {}

def _fmt_exc(e: Exception) -> str:
    return f"{e.__class__.__name__}: {e!r}"

def _read_file_cached(path: str) -> Optional[str]:
    if not path:
        return None
    if path in _PROMPT_CACHE:
        return _PROMPT_CACHE[path]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            _PROMPT_CACHE[path] = fh.read()
            return _PROMPT_CACHE[path]
    except Exception:
        _PROMPT_CACHE[path] = None
        return None

def _ctx_dbg(msg: str, *, once: bool = False) -> None:
    """Debug log gated by COPYCLIP_DEBUG; set once=True to de-dup."""
    if once:
        if msg in _LOG_ONCE_KEYS:
            return
        _LOG_ONCE_KEYS.add(msg)
    if _DEBUG:
        print(f"[CTX] {msg}", file=sys.stderr)


class _Spinner:
    """Tiny TTY spinner for long operations (no deps). Use as context manager."""
    FRAMES = ("⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏")
    ASCII_FRAMES = ("|","/","-","\\")
    def __init__(self, label: str, *, stream = sys.stderr):
        self.start_time = time.time()
        self.label = label
        self.stream = stream
        self.enabled = _PROGRESS and hasattr(stream, "isatty") and stream.isatty()
        self._stop = threading.Event()
        self._suffix = ""
        self._t: Optional[threading.Thread] = None
        self._status: Optional[str] = None  # "ok" | "err" | None
        # choose frames (avoid unicode on non-UTF consoles)
        try:
            "✓".encode(stream.encoding or "utf-8")
            self._frames = self.FRAMES
            self._ok = "✓"
            self._err = "✗"
        except Exception:
            self._frames = self.ASCII_FRAMES
            self._ok = "+"
            self._err = "x"

    def __enter__(self):
        if self.enabled:
            self._t = threading.Thread(target=self._run, daemon=True)
            self._t.start()
        else:
            # minimal, non-TTY: single line start
            self._write(f"{self.label} ...\n")
        return self

    def __exit__(self, exc_type, exc, tb):
        # If we've already reported a status, don't print another line.
        if self._status is not None:
            return
        if exc:
            self.fail("error")
        else:
            self.success("done")

    def stage(self, msg: str):
        self._suffix = f" — {msg}"

    def success(self, msg: str = "done"):
        if self.enabled:
            self._stop.set()
            if self._t:
                self._t.join(timeout=0.2)
            self._write(f"\r{self._ok} {self.label}{(' — ' + msg) if msg else ''}\x1b[K\n")
        else:
            # non-TTY already printed a start; add completion line
            self._write(f"{self._ok} {self.label} — {msg}\n")
        self._status = "ok"

    def fail(self, msg: str = "failed"):
        if self.enabled:
            self._stop.set()
            if self._t:
                self._t.join(timeout=0.2)
            self._write(f"\r{self._err} {self.label}{(' — ' + msg) if msg else ''}\x1b[K\n")
        else:
            self._write(f"{self._err} {self.label} — {msg}\n")
        self._status = "err"

    # internals
    def _run(self):
        i = 0
        while not self._stop.is_set():
            f = self._frames[i % len(self._frames)]
            self._write(f"\r{f} {self.label}{self._suffix}\x1b[K")
            i += 1
            time.sleep(0.09)

    def _write(self, s: str):
        try:
            self.stream.write(s)
            self.stream.flush()
        except Exception:
            pass

# Brief: _collapse_blank_lines
def _collapse_blank_lines(text: str) -> str:
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

# ---------------------------------------------------------------------------
# Helpers (existing + small tweaks)
# ---------------------------------------------------------------------------

# Brief: _run_coro_sync
def _run_coro_sync(coro_or_fn, *, timeout_s: Optional[float] = None):
    if callable(coro_or_fn) and not asyncio.iscoroutine(coro_or_fn):
        maybe = coro_or_fn()
        if not asyncio.iscoroutine(maybe):
            return maybe
        coro = maybe
    else:
        coro = coro_or_fn
    if not asyncio.iscoroutine(coro):
        return coro
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    q: "queue.Queue[Tuple[bool, object]]" = queue.Queue()
    def runner():
        try:
            res = asyncio.run(coro)
            q.put((True, res))
        except Exception as e:
            q.put((False, e))
    t = threading.Thread(target=runner, daemon=True)
    t.start()
    
    timeout = timeout_s if timeout_s is not None else float(os.getenv("COPYCLIP_LLM_TIMEOUT", "60"))
    try:
        ok, val = q.get(timeout=timeout)
    except queue.Empty:
        raise TimeoutError(f"LLM task timed out after {timeout}s")
    if ok:
        return val
    raise val

# Brief: _ctx_log
def _ctx_log(msg: str) -> None:
    print(f"[CTX] {msg}", file=sys.stderr)

# Brief: _line_offsets
def _line_offsets(text: str) -> List[int]:
    offsets = [0]
    for match in re.finditer(r"\n", text):
        offsets.append(match.end())
    return offsets

# Brief: _shorten_sig_py_from_ast
def _shorten_sig_py_from_ast(node: ast.AST, src: str) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    lines: List[str] = []
    for d in getattr(node, "decorator_list", []):
        deco = ast.get_source_segment(src, d) or ast.unparse(d)
        if not deco.startswith("@"):
            deco = "@" + deco
        lines.append(deco)
    name = node.name
    args = node.args

    def _ann(a: Optional[ast.AST]) -> str:
        return f": {ast.get_source_segment(src, a) or ast.unparse(a)}" if a else ""

    parts: List[str] = []
    # pos-only
    posonlyargs = getattr(args, "posonlyargs", [])
    for i, a in enumerate(posonlyargs):
        default = None
        if args.defaults:
            # defaults array covers both posonlyargs and args combined
            total_positional = len(posonlyargs) + len(args.args)
            di = i - (total_positional - len(args.defaults))
            if di >= 0:
                default = args.defaults[di]
        seg = a.arg + _ann(a.annotation)
        if default is not None:
            seg += "=" + (ast.get_source_segment(src, default) or ast.unparse(default))
        parts.append(seg)
    
    # Add pos-only separator after pos-only args
    if posonlyargs:
        parts.append("/")

    # normal args
    base_idx = len(getattr(args, "posonlyargs", []))
    for i, a in enumerate(args.args):
        default = None
        if args.defaults:
            di = i - (len(args.args) - len(args.defaults))
            if di >= 0:
                default = args.defaults[di]
        seg = a.arg + _ann(a.annotation)
        if default is not None:
            seg += "=" + (ast.get_source_segment(src, default) or ast.unparse(default))
        parts.append(seg)

    # vararg
    if args.vararg:
        seg = "*" + args.vararg.arg
        if getattr(args.vararg, "annotation", None):
            seg += _ann(args.vararg.annotation)
        parts.append(seg)
    elif args.kwonlyargs:
        parts.append("*")

    # kw-only
    for i, a in enumerate(args.kwonlyargs):
        default = args.kw_defaults[i]
        seg = a.arg + _ann(a.annotation)
        if default is not None:
            seg += "=" + (ast.get_source_segment(src, default) or ast.unparse(default))
        parts.append(seg)

    # kwarg
    if args.kwarg:
        seg = "**" + args.kwarg.arg
        if getattr(args.kwarg, "annotation", None):
            seg += _ann(args.kwarg.annotation)
        parts.append(seg)

    ret = ""
    if node.returns:
        ret_src = ast.get_source_segment(src, node.returns) or ast.unparse(node.returns)
        ret = f" -> {ret_src}"

    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    sig = prefix + name + "(" + ", ".join(parts) + ")" + ret + ":"
    lines.append(sig)
    return "\n".join(lines)

# Brief: _google_docstring_for_symbol
def _google_docstring_for_symbol(signature_text: str,
                                 name: str,
                                 kind: str,
                                 called: Tuple[str, ...],
                                 raises: Tuple[str, ...],
                                 doc_lang: str = "en",
                                 param_types: Tuple[str, ...] = (),
                                 return_annotation: str = "",
                                 side_effects: Tuple[str, ...] = ()) -> List[str]:
    """Generate meaningful Google-style docstrings based on structural context."""

    params = []
    if param_types:
        for p in param_types:
            if ":" in p:
                name_part, type_part = p.split(":", 1)
                params.append((name_part.strip(), type_part.strip()))
            else:
                params.append((p, "Any"))
    else:
        # Simple extraction from signature
        m = re.search(r"\((.*?)\)", signature_text)
        if m:
            inside = m.group(1).strip()
            if inside:
                for tok in inside.split(","):
                    tok = tok.strip()
                    if not tok or tok.startswith("*"):
                        continue
                    if ":" in tok:
                        name_part, type_part = tok.split(":", 1)
                        name_part = name_part.split("=")[0].strip()
                        type_part = type_part.split("=")[0].strip()
                        params.append((name_part, type_part))
                    else:
                        name_part = tok.split("=")[0].strip()
                        params.append((name_part, "Any"))

    
    # Generate specific summary based on function name and calls
    if name == "main":
        summary = "Command-line interface entry point."
    elif "split" in name.lower():
        summary = f"Split input data into smaller chunks."
    elif "parse" in name.lower():
        summary = f"Parse and validate input data."
    elif called and any("AudioSegment" in c for c in called):
        summary = "Process audio data using pydub."
    else:
        summary = f"Execute {name} operation."
    
    lines = ['"""' + summary]
    
    # Args section with better descriptions
    if params:
        lines.append("")
        lines.append("Args:")
        for pname, ptype in params:
            # Generate meaningful descriptions based on parameter names
            if "path" in pname.lower():
                desc = "Path to the file"
            elif "duration" in pname.lower():
                desc = "Duration in seconds"
            elif "chunk" in pname.lower():
                desc = "Size or number of chunks"
            else:
                desc = f"The {pname} value"
            
            lines.append(f"    {pname}: {desc}.")
    
    # Returns section with types
    if return_annotation and return_annotation != "None":
        lines.append("")
        lines.append("Returns:")
        lines.append(f"    {return_annotation}")
    elif "->" in signature_text:
        ret_type = signature_text.split("->", 1)[1].strip().rstrip(":")
        if ret_type and ret_type != "None":
            lines.append("")
            lines.append("Returns:")
            lines.append(f"    {ret_type}")
    
    # Raises section (be specific)
    if raises:
        lines.append("")
        lines.append("Raises:")
        for r in raises[:5]:  # Limit to 5
            if "FileNotFound" in r:
                lines.append(f"    {r}: If input file doesn't exist.")
            elif "ValueError" in r:
                lines.append(f"    {r}: If parameters are invalid.")
            else:
                lines.append(f"    {r}: On operation failure.")
    
    # Side-effects (full descriptions)
    if side_effects:
        lines.append("")
        lines.append("Side-effects:")
        for se in side_effects:
            if se == "file I/O":
                lines.append("    Reads from or writes to filesystem.")
            elif se == "network I/O":
                lines.append("    Makes network requests.")
            elif se == "console output":
                lines.append("    Prints to stdout/stderr.")
            elif se == "filesystem":
                lines.append("    Modifies filesystem structure.")
            elif se == "process":
                lines.append("    Spawns subprocesses.")
            else:
                lines.append(f"    {se}")
    
    # Calls (most important ones)
    if called:
        # Filter: keep only dotted names (module.func) and exclude common built-ins
        builtins = {"print", "len", "range", "open", "str", "int", "float", "list", "dict", "set", "tuple", "bool"}
        important = []
        for c in called:
            if "." in c:  # Keep all dotted names
                # Format with parens
                important.append(f"{c}()")
            elif c not in builtins and not c.startswith("_"):
                # Non-builtin, non-private local - skip unless it's a known important name
                pass
        important = important[:5]  # Limit to 5
        if important:
            lines.append("")
            lines.append("Calls:")
            lines.append(f"    {', '.join(important)}")
    
    lines.append('"""')
    return lines

# ---------------------------------------------------------------------------
# 1) CONTEXTUAL MINIMIZATION (radically enhanced)
#    - Module summary block
#    - Preserve imports at file top
#    - Keep calls/returns/raises inside defs
#    - Optional Google-style docstrings
# ---------------------------------------------------------------------------

async def _llm_contextual_minimize(content: str, 
                                   file_ext: str, 
                                   doc_lang: str,
                                   model_hint: Optional[str] = None) -> str:
    """Use LLM to generate full contextual minimization."""
    cfg = load_config(os.getenv("COPYCLIP_LLM_CONFIG"))
    s = resolve_settings(cfg,
                        cli_provider=os.getenv("COPYCLIP_LLM_PROVIDER"),
                        cli_model=os.getenv("COPYCLIP_LLM_MODEL") or model_hint,
                        cli_endpoint=os.getenv("COPYCLIP_LLM_ENDPOINT"),
                        cli_timeout=int(os.getenv("COPYCLIP_LLM_TIMEOUT", "60") or 60))
    _ctx_dbg("settings:\n" + pretty_settings(s), once=True)

    client = LLMClientFactory.create(
        s["provider"], 
        api_key=s.get("api_key"), 
        model=s.get("model"),
        endpoint=s.get("endpoint"), 
        timeout=int(s.get("timeout") or 30),
        extra_headers=s.get("extra_headers") or {}
    )
    
    # Check for contextual minimizer prompt
    prompt_path = os.path.join(os.path.dirname(__file__), "llm", "prompts", "contextual_minimizer.md")
    system_prompt: Optional[str] = None
    if os.path.exists(prompt_path) and os.path.isfile(prompt_path):
        _ctx_dbg(f"Using contextual minimizer prompt from {prompt_path}", once=True)
        system_prompt = _read_file_cached(prompt_path)
    
    try:
        if hasattr(client, 'minimize_code_contextually'):
            result = await client.minimize_code_contextually(
                content, file_ext, doc_lang, system_prompt
            )
            def _postprocess_minimized(s: str) -> str:
                s = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", s.strip(), flags=re.M)
                s = _collapse_blank_lines(s)
                if not s.endswith("\n"):
                    s += "\n"
                return s
            return _postprocess_minimized(result)
        else:
            _ctx_log("Client doesn't have minimize_code_contextually method")
            raise Exception("Method not available")
            
    except Exception as e:
        # Let caller decide how/what to log; include full type info
        raise RuntimeError(_fmt_exc(e)) from e

def _get_return_stub(return_annotation: str) -> str:
    """Generate appropriate return stub based on type annotation."""
    if not return_annotation or return_annotation == "None":
        return ""
    elif "list" in return_annotation.lower() or "List" in return_annotation:
        return "return []"
    elif "dict" in return_annotation.lower() or "Dict" in return_annotation:
        return "return {}"
    elif "str" in return_annotation.lower():
        return 'return ""'
    elif "int" in return_annotation.lower():
        return "return 0"
    elif "bool" in return_annotation.lower():
        return "return False"
    else:
        return "return None"

# Brief: _python_collect_defined_names
def _python_collect_defined_names(tree: ast.AST) -> Set[str]:
    names: Set[str] = set()
    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, n): names.add(n.name)
        def visit_AsyncFunctionDef(self, n): names.add(n.name)
        def visit_ClassDef(self, n):
            names.add(n.name)
            for b in n.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(b.name)
    V().visit(tree)
    return names

# Brief: _python_extract_file_imports
def _python_extract_file_imports(content: str) -> List[str]:
    try:
        tree = ast.parse(content or "")
    except Exception:
        return []
    imports: List[Tuple[int, str]] = []
    body = tree.body
    i = 0
    # saltar docstring de módulo
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), (ast.Str, ast.Constant)):
        i = 1
    for node in body[i:]:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            seg = ast.get_source_segment(content, node)
            if not seg:
                if isinstance(node, ast.Import):
                    seg = "import " + ", ".join(n.name for n in node.names)
                else:
                    base = "." * (node.level or 0) + (node.module or "")
                    seg = f"from {base} import " + ", ".join(n.name for n in node.names)
            imports.append((node.lineno, seg.rstrip()))
        else:
            break
    imports.sort(key=lambda x: x[0])
    return [s for _, s in imports]

# Brief: _python_minimize_function_body
def _python_minimize_function_body(original_lines: List[str], indent: str, defined: Set[str],
                                   return_annotation: str = "") -> List[str]:
    kept, has_return = [], False
    call_pat = re.compile(r"\b(" + "|".join(map(re.escape, sorted(defined))) + r")\s*\(") if defined else None
    for line in original_lines:
        s = line.strip()
        if s.startswith("return "):
            kept.append(line); has_return = True
        elif s.startswith("raise "):
            kept.append(line)
        elif call_pat and call_pat.search(s):
            kept.append(line)
    if not kept:
        stub = _get_return_stub(return_annotation)
        if stub:
            kept = [indent + "...", indent + stub]
        else:
            kept = [indent + "..."]
    elif not has_return and return_annotation and return_annotation != "None":
        # Add return stub if function should return something but no return was kept
        stub = _get_return_stub(return_annotation)
        if stub:
            kept.append(indent + stub)
    return kept

# Brief: _python_render_intelligent
def _python_render_intelligent(content: str, docstrings_mode: str, doc_lang: str) -> str:
    """
        Render a Python file with:
          - module summary docstring (heuristic)
          - preserved top imports
          - defs/classes with essential lines
          - Google-style docstrings when requested
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """


    try:
        tree = ast.parse(content or "")
    except Exception:
        return content

    # module + symbol context for summaries
    mod_ctx, symbols = extract_python_context(content)

    # 1) Module docstring (summary) – derived from context
    out: List[str] = []
    existing_module_doc = None
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(getattr(tree.body[0], "value", None), (ast.Str, ast.Constant)):
        existing_module_doc = ast.get_source_segment(content, tree.body[0])
    
    title = (mod_ctx.module_name or "module")
    if existing_module_doc:
        # Keep original docstring, add summary as comments
        out.append(existing_module_doc)
        out.append("")
        if mod_ctx.inferred_responsibilities:
            out.append("# Responsibilities: " + ", ".join(mod_ctx.inferred_responsibilities))
        if mod_ctx.public_symbol_names:
            out.append("# Public API: " + ", ".join(mod_ctx.public_symbol_names))
        if mod_ctx.external_dependencies:
            out.append("# External deps: " + ", ".join(mod_ctx.external_dependencies))
        if out[-1] != "":
            out.append("")
    else:
        # Create new docstring
        module_summary = ['"""' + title + " module."]
        if mod_ctx.inferred_responsibilities:
            module_summary.append("")
            module_summary.append("Responsibilities: " + ", ".join(mod_ctx.inferred_responsibilities))
        if mod_ctx.public_symbol_names:
            module_summary.append("")
            module_summary.append("Public API: " + ", ".join(mod_ctx.public_symbol_names))
        if mod_ctx.external_dependencies:
            module_summary.append("")
            module_summary.append("External deps: " + ", ".join(mod_ctx.external_dependencies))
        module_summary.append('"""')
        out.append("\n".join(module_summary))
        out.append("")

    # 2) Preserve top imports
    imports = _python_extract_file_imports(content)
    if imports:
        out.extend(imports)
        out.append("")

    defined = _python_collect_defined_names(tree)
    lines = content.splitlines(True)  # keep EOLs for slicing

    # quick index for docstrings (overwrite or insert)
    docs_by_symbol: Dict[str, str] = {}
    if docstrings_mode in ("generate", "overwrite"):
        docs_map = generate_docstrings_for_file(
            content, file_ext="py", lang=doc_lang, level="heuristic", model_hint=None
        )
        docs_by_symbol = docs_map  # keys: f"{module_name}:__module__" and symbol paths

    # utility: fetch ContextRecord for a symbol path
    by_name: Dict[str, Tuple[str, Tuple[str, ...], Tuple[str, ...]]] = {}
    for s in symbols:
        by_name[s.name] = (s.signature_text, s.called_names, s.raise_names)



    # 3) Re-render each top-level definition
    class Renderer(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef):
            # Add one-line comment before function
            ctx_record = next((s for s in symbols if s.name == node.name), None)

            func_info = by_name.get(node.name, (None, (), ()))
            called = func_info[1] if func_info else ()
            
            # Generate meaningful one-line comment
            if node.name == "main":
                comment = "# Entry point that parses arguments and orchestrates execution"
            elif "split" in node.name.lower():
                comment = f"# Split {node.name[6:] if node.name.startswith('split_') else 'data'} into smaller parts"
            elif "parse" in node.name.lower():
                comment = f"# Parse and validate {node.name[6:] if node.name.startswith('parse_') else 'input'}"
            elif ctx_record and ctx_record.called_names:
                main_call = ctx_record.called_names[0] if ctx_record.called_names else ""
                comment = f"# Orchestrate {main_call.split('.')[-1] if main_call else 'operations'}"
            else:
                comment = f"# Execute {node.name} logic"
            
            out.append(comment)
            
            # Add the signature
            sig_text = _shorten_sig_py_from_ast(node, content)
            out.append(sig_text)
            indent = " " * (node.col_offset + 4)

            # Generate docstring if requested
            if docstrings_mode in ("generate", "overwrite"):
                if ctx_record:
                    ds_lines = _google_docstring_for_symbol(
                        sig_text, node.name, "function", 
                        ctx_record.called_names, 
                        ctx_record.raise_names,
                        doc_lang,
                        ctx_record.param_types,
                        ctx_record.return_annotation,
                        ctx_record.side_effects
                    )
                else:
                    # Fallback with empty tuples
                    ds_lines = _google_docstring_for_symbol(
                        sig_text, node.name, "function", 
                        (), (), doc_lang
                    )
                out.extend([indent + l if l else "" for l in ds_lines])


            # Minimize body intelligently
            start = node.body[0].lineno if node.body else node.lineno + 1
            end = getattr(node, "end_lineno", start)
            body_lines = lines[start - 1: end]
            ret_ann = ""
            if node.returns:
                ret_ann = ast.get_source_segment(content, node.returns) or ast.unparse(node.returns)
            kept = _python_minimize_function_body(body_lines, indent, defined, ret_ann)

            
            # Replace generic "logic omitted" with more specific placeholder
            kept = [l.replace("# ... logic omitted ...", "...") if "logic omitted" in l else l for l in kept]
            
            out.extend(kept)
            out.append("")

    Renderer().visit(tree)
    # always end with newline

    # Mermaid (gated)
    if os.getenv("COPYCLIP_MERMAID", "1") == "1":
        mermaid_max = int(os.getenv("COPYCLIP_MERMAID_MAX", "30"))
        if len(defined) <= mermaid_max:
            mermaid_lines = ["", "```mermaid", "graph TD"]
            relationships = set()

            for sym in symbols:
                if sym.called_names:
                    for called in sym.called_names[:5]:  # Limit to prevent clutter
                        if "." in called:
                            # External module reference - use dotted line
                            module = called.split(".")[0]
                            relationships.add((sym.name, module, "dotted"))
                        elif called in defined:
                            # Internal reference - use solid line
                            relationships.add((sym.name, called, "solid"))

            # Add nodes
            for name in sorted(defined):
                mermaid_lines.append(f"    {name}")

            # Add edges with proper style
            for source, target, style in sorted(relationships):
                if style == "dotted":
                    mermaid_lines.append(f"    {source} -.-> {target}")
                else:
                    mermaid_lines.append(f"    {source} --> {target}")

            mermaid_lines.append("```")
            out.extend(mermaid_lines)

    return ("\n".join(out)).rstrip() + "\n"

# ---------------- JS/TS (heuristic but effective) -----------------------------

_JS_FUNC_START = re.compile(
    r"""
    ^\s*(?:
        (?P<export>export\s+)?(?P<async>async\s+)?function\s+(?P<fname>[A-Za-z_$][A-Za-z0-9_$]*)\s*\(|   # function foo(
        (?P<cls>(?P<cls_export>export\s+)?class\s+(?P<cname>[A-Za-z_$][A-Za-z0-9_$]*))\b                 |   # class Foo / export class Foo
        (?P<var>(?P<var_export>export\s+)?(?:const|let|var)\s+(?P<aname>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?P<arrow>async\s*)?\([^)]*\)\s*=>)  # (export) const foo = (...) =>
    )
    """,
    re.VERBOSE,
)

# Nuevo método para procesar múltiples archivos concurrentemente
async def batch_minimize_contextually(files_dict, file_ext, doc_lang, provider=None):
    """Procesa múltiples archivos en paralelo con rate limiting."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    # Límite de concurrencia basado en el proveedor
    PROVIDER_LIMITS = {
        'deepseek': 10,  # DeepSeek permite más concurrencia
        'openai': 5,
        'anthropic': 3
    }
    
    provider_name = provider or os.getenv("COPYCLIP_LLM_PROVIDER", "deepseek")
    max_concurrent = PROVIDER_LIMITS.get(provider_name.lower(), 3)
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_single_file(filepath, content):
        async with semaphore:
            start = time.time()
            try:
                result, settings = await contextual_minimize(
                    content, file_ext, doc_lang, provider_hint=provider
                )
                elapsed = time.time() - start
                print(f"[INFO] {filepath}: {len(content)} → {len(result)} chars in {elapsed:.2f}s", 
                      file=sys.stderr)
                return filepath, result
            except Exception as e:
                print(f"[ERROR] {filepath}: {e}", file=sys.stderr)
                return filepath, content  # Retorna original si falla
    
    tasks = [process_single_file(fp, content) 
             for fp, content in files_dict.items()]
    
    results = await asyncio.gather(*tasks)
    return dict(results)

# Brief: _jsts_collect_top_imports
def _jsts_collect_top_imports(content: str) -> List[str]:
    lines = content.splitlines()
    out: List[str] = []
    for ln in lines:
        t = ln.strip()
        if not t:
            continue
        if (t.startswith("import ")
            or (t.startswith("export ") and " from " in t)
            or t.startswith("require(")):
            out.append(ln.rstrip())
            continue
        if out:  # primera no-import -> cortar
            break
        if t.startswith("//") or t.startswith("/*"):
            continue
    return out

# Brief: _jsts_brace_span
def _jsts_brace_span(lines: List[str], start_idx: int) -> int:
    """
    
        Given a line that opens a block '{', return the index of the line where that block ends.
        Best-effort; handles nested braces by counting.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    depth = 0
    i = start_idx
    opened = False
    while i < len(lines):
        depth += lines[i].count("{")
        depth -= lines[i].count("}")
        if lines[i].strip().endswith("{"):
            opened = True
        if opened and depth <= 0:
            return i
        i += 1
    return min(len(lines) - 1, start_idx)

# Brief: _jsts_minimize_block
def _jsts_minimize_block(body_lines: List[str], base_indent: str, defined: Set[str]) -> List[str]:
    kept: List[str] = []
    omitted = False
    call_pat = None
    if defined:
        call_pat = re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(defined)) + r")\s*\(")
    for raw in body_lines:
        line = raw.rstrip("\n")
        s = line.strip()
        keep = False
        if s.startswith("return ") or s == "return;":
            keep = True
        elif s.startswith("throw "):
            keep = True
        elif call_pat and call_pat.search(s):
            keep = True
        if keep:
            omitted = False
            kept.append(line)
        else:
            if not omitted:
                kept.append(base_indent + "/* ... logic omitted ... */")
                omitted = True
    if not kept:
        kept = [base_indent + "/* ... logic omitted ... */"]
    return kept

# Brief: _jsts_render_intelligent
def _jsts_render_intelligent(content: str, ext: str, docstrings_mode: str, doc_lang: str) -> str:
    # Module summary (block comment) using structural context
    mod, symbols = extract_jsts_context(content, module_path=None)
    header: List[str] = ["/**"]
    header.append(f"{mod.module_name} module")
    if mod.public_symbol_names:
        header.append("")
        header.append("Public API: " + ", ".join(mod.public_symbol_names))
    if mod.external_dependencies:
        header.append("")
        header.append("External deps: " + ", ".join(mod.external_dependencies))
    header.append("*/")
    out: List[str] = ["\n".join(header), ""]

    # preserve top imports
    imports = _jsts_collect_top_imports(content)
    if imports:
        out.extend(imports)
        out.append("")

    # local defined names (for call retention)
    defined = js_ts_collect_local_symbols(content)

    # simple state machine to copy signatures + minimized bodies
    lines = content.splitlines(True)
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = _JS_FUNC_START.match(ln)
        if not m:
            i += 1
            continue

        if m.group("cname"):  # class
            cname = m.group("cname")
            out.append(ln.rstrip())

            # localizar llaves de la clase
            brace_line = i
            if "{" not in lines[brace_line]:
                while brace_line < len(lines) and "{" not in lines[brace_line]:
                    brace_line += 1
            end_idx = _jsts_brace_span(lines, brace_line)
            body = lines[brace_line+1:end_idx]

            # extraer métodos simples:  foo(...) {  /  async foo(...) {
            
            method_regex = re.compile(
                r'^\s*(?P<async>async\s+)?(?P<mname>[A-Za-z_$][A-Za-z0-9_$]*)\s*\((?P<params>[^)]*)\)\s*(?:\{|$)', 
                re.M
            )

            base_indent = re.match(r"^(\s*)", lines[i]).group(1) if i < len(lines) else ""
            method_indent = base_indent + "    "
            emitted_any = False
            
            for meth in method_regex.finditer("".join(body)):
                mname = meth.group("mname")
                params = meth.group("params").strip()
                is_async = bool(meth.group("async"))
                
                # Skip constructor for now (handle separately if needed)
                if mname == "constructor":
                    continue
                    
                # One-line comment
                out.append(method_indent + f"// {mname}: method operation")
                
                # JSDoc if enabled
                if docstrings_mode != "off":
                    out.append(method_indent + "/**")
                    if params:
                        for p in [p.strip().split(":")[0].strip() for p in params.split(",") if p.strip()]:
                            out.append(method_indent + f" * @param {p}")
                    out.append(method_indent + " * @returns {void}")
                    out.append(method_indent + " */")
                
                # Method signature with minimized body
                async_prefix = "async " if is_async else ""
                out.append(method_indent + f"{async_prefix}{mname}({params}) {{ /* ... logic omitted ... */ }}")
                emitted_any = True

            if not emitted_any:
                out.append(method_indent + "/* methods omitted for brevity */")

            out.append(re.match(r"^(\s*)", lines[brace_line]).group(1) + "}")
            out.append("")
            i = end_idx + 1
            continue


        # function or arrow function declaration
        out.append(ln.rstrip())
        # find function body block
        brace_line = i
        while brace_line < len(lines) and "{" not in lines[brace_line]:
            # si es arrow sin llaves en la MISMA línea (=> expr;)
            if "=>" in lines[brace_line] and "{" not in lines[brace_line]:
                # Reescribe arrow one-liner a forma bloque, evitando sintaxis inválida.
                line = out[-1].rstrip()
                line2 = re.sub(r"=>\s*[^;]+;?$", "=> { /* ... logic omitted ... */ }", line)
                if line2 == line:
                    line2 = line.rstrip(";") + " { /* ... logic omitted ... */ }"
                out[-1] = line2
                out.append("")
                i = brace_line + 1
                break
            brace_line += 1
        else:
            # no se encontró '{' ni arrow esperado: continuar
            i += 1
            continue
        
        if brace_line < len(lines) and "{" in lines[brace_line]:
            end_idx = _jsts_brace_span(lines, brace_line)
            body = lines[brace_line+1:end_idx]
            indent = re.match(r"^(\s*)", lines[brace_line]).group(1) + "    "
            kept = _jsts_minimize_block(body, indent, defined)
            out.extend(kept)
            out.append("}")
            out.append("")
            i = end_idx + 1

    # If nothing matched, return original content (fallback)
    final = ("\n".join(out)).rstrip() + "\n"
    return final

# ---------------------------------------------------------------------------
# Existing path: structural/basic/aggressive kept as-is (with small fixes)
# ---------------------------------------------------------------------------

# Brief: extract_functions
def extract_functions(content: str, lang: str) -> List[Dict]:
    if lang == "python":
        return _extract_python_functions(content)
    elif lang in ("javascript", "typescript"):
        return _extract_js_functions(content)
    return []

# Brief: _extract_python_functions
def _extract_python_functions(content: str) -> List[Dict]:
    results: List[Dict] = []
    try:
        tree = ast.parse(content)
    except Exception:
        return results
    line_offsets = _line_offsets(content)
    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            self._add(node, "function")
        def visit_AsyncFunctionDef(self, node):
            self._add(node, "function")
        def visit_ClassDef(self, node):
            self._add(node, "class")
            self.generic_visit(node)
        def _add(self, node, typ):
            start_line = node.lineno
            end_line = getattr(node, "end_lineno", start_line)
            lines = content.splitlines()
            snippet_lines = lines[start_line - 1 : min(end_line + 2, len(lines))]
            snippet = "\n".join(snippet_lines)
            start_offset = line_offsets[start_line - 1]
            end_offset = line_offsets[min(end_line, len(line_offsets)-1)] if end_line < len(line_offsets) else len(content)
            results.append({
                "name": node.name if hasattr(node, "name") else "anonymous",
                "type": typ,
                "start_line": start_line,
                "end_line": end_line,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "code": snippet,
                "lang": "python",
            })
    V().visit(tree)
    return results

_JS_DECL = re.compile(
    r"""
    (?P<func>^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<fname>[A-Za-z_$][A-Za-z0-9_$]*)\s*\()|
    (?P<class>^\s*(?:export\s+)?class\s+(?P<cname>[A-Za-z_$][A-Za-z0-9_$]*)\b)|
    (?P<arrow>^\s*(?:const|let|var)\s+(?P<aname>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)
    """,
    re.VERBOSE | re.MULTILINE,
)

# Brief: _extract_js_functions
def _extract_js_functions(content: str) -> List[Dict]:
    """
    
        Enhanced JS/TS extractor:
          - finds top-level functions, classes and arrow functions
          - for classes, also attempts to extract method names defined inside the class body
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    results: List[Dict] = []
    lines = content.splitlines()
    line_offsets = _line_offsets(content)
    for m in _JS_DECL.finditer(content):
        name = m.group("fname") or m.group("cname") or m.group("aname") or "anonymous"
        typ = "class" if m.group("cname") else "function"
        start_offset = m.start()
        start_line = content.count("\n", 0, start_offset) + 1

        # Default snippet window
        default_end_line = min(start_line + 4, len(lines))

        # If this is a class, try to capture its body and extract method names
        if m.group("cname"):
            # Find the snippet for the class (best-effort using character offsets)
            brace_pos = content.find("{", start_offset)
            end_pos = -1
            if brace_pos != -1:
                depth = 0
                i = brace_pos
                while i < len(content):
                    if content[i] == "{":
                        depth += 1
                    elif content[i] == "}":
                        depth -= 1
                        if depth == 0:
                            end_pos = i
                            break
                    i += 1

            if brace_pos != -1 and end_pos != -1:
                # Convert to line numbers/snippet using existing helpers
                start_line_snip = content.count("\n", 0, start_offset) + 1
                end_line = content.count("\n", 0, end_pos) + 1
                snippet = "\n".join(lines[start_line_snip - 1 : end_line])
                end_offset = line_offsets[end_line - 1] if end_line - 1 < len(line_offsets) else len(content)
            else:
                # Fallback to a small window if we couldn't locate braces
                end_line = min(start_line + 4, len(lines))
                snippet = "\n".join(lines[start_line - 1 : end_line])
                end_offset = line_offsets[end_line - 1] if end_line - 1 < len(line_offsets) else len(content)

            results.append({
                "name": name,
                "type": typ,
                "start_line": start_line,
                "end_line": end_line,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "code": snippet,
                "lang": "javascript",
            })

            # Extract method-like names inside class body using character-range scanning
            if brace_pos != -1 and end_pos != -1 and end_pos > brace_pos + 1:
                body_text = content[brace_pos + 1 : end_pos]
                for mm in re.finditer(r'^\s*(?:async\s+)?(?P<mname>[A-Za-z_$][A-Za-z0-9_$]*)\s*\(', body_text, re.MULTILINE):
                    mname = mm.group("mname")
                    method_abs_offset = brace_pos + 1 + mm.start()
                    method_start_line = content.count("\n", 0, method_abs_offset) + 1
                    method_end_line = min(method_start_line + 4, len(lines))
                    method_snippet = "\n".join(lines[method_start_line - 1:method_end_line])
                    method_end_offset = line_offsets[method_end_line - 1] if method_end_line - 1 < len(line_offsets) else len(content)
                    results.append({
                        "name": mname,
                        "type": "function",
                        "start_line": method_start_line,
                        "end_line": method_end_line,
                        "start_offset": method_abs_offset,
                        "end_offset": method_end_offset,
                        "code": method_snippet,
                        "lang": "javascript",
                    })
        else:
            # function or arrow function - keep previous behavior
            end_line = default_end_line
            snippet = "\n".join(lines[start_line - 1 : end_line])
            end_offset = line_offsets[end_line - 1] if end_line - 1 < len(line_offsets) else len(content)
            results.append({
                "name": name,
                "type": typ,
                "start_line": start_line,
                "end_line": end_line,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "code": snippet,
                "lang": "javascript",
            })

    # Debug: log extracted JS symbols for validation in tests (to stderr)
    try:
        _ctx_log("JS symbols extracted: " + ", ".join(sorted({r["name"] for r in results})))
    except Exception:
        ...
    return results

# Brief: inject_comments
def inject_comments(content: str, funcs: List[Dict], descs: List[str]) -> str:
    lines = content.splitlines()
    funcs_descs = sorted(zip(funcs, descs), key=lambda x: x[0]["start_line"], reverse=True)
    for func, desc in funcs_descs:
        if not desc or not str(desc).strip():
            continue
        comment = "# " + desc if func["lang"] == "python" else "// " + desc
        insert_at = func["start_line"] - 1
        if insert_at == 0:
            lines.insert(0, comment)
        elif lines[insert_at - 1].strip() == "":
            lines[insert_at - 1] = comment
        else:
            lines.insert(insert_at, comment)
    return "\n".join(lines) + "\n"

# --------------------- LEGACY CONTEXTUAL (kept for tests) --------------------

# Brief: _heuristic_desc
def _heuristic_desc(name: str, typ: str) -> str:
    if typ == "class":
        return f"Class {name}: container for related behavior"
    return f"Function {name}: core operation"

# Brief: _build_contextual_skeleton
def _build_contextual_skeleton(funcs: List[Dict], descs: List[str], lang: str, *, doc_mode: str = "off") -> str:
    parts: List[str] = []
    module_comment = "Module: Contextual minimization of source code"
    parts.append(("# " if lang == "python" else "// ") + module_comment + "\n")
    # Pair available descriptions with functions; if there are extra descriptions,
    # include them as additional module-level comments to avoid losing mocked responses.
    paired = sorted(zip(funcs, descs), key=lambda x: x[0]["start_line"])
    for f, d in paired:
        desc = (d or "").strip() or _heuristic_desc(f["name"], f["type"])
        header = "# " + desc if lang == "python" else "// " + desc
        sig = (f["code"].splitlines() or [""])[0].strip()
        if lang == "python":
            # normalize line ending to have a colon
            sig = sig.rstrip()
            if not sig.endswith(":"):
                sig = sig + ":"
            parts.append(header)
            parts.append(sig)
            if doc_mode != "off" and desc:
                parts.append("    " + '"""' + desc + '"""')
            parts.append("    pass")
        else:
            parts.append(header)
            parts.append(sig if "{" in sig else (sig + " { /* ... */ }"))
        parts.append("")
    # If there are more descriptions than functions, add them as extra module comments
    if len(descs) > len(funcs):
        for extra in descs[len(funcs):]:
            if not extra or not str(extra).strip():
                continue
            parts.insert(1, ("# " if lang == "python" else "// ") + extra)
    return ("\n".join(parts)).rstrip() + "\n"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Brief: _contextual_llm_descriptions
def _contextual_llm_descriptions(content: str, language: str, doc_lang: str, model_hint: Optional[str]) -> List[str]:
    """
    
        Usa el pipeline de docstrings (que ya sabe hablar con el LLM)
        para obtener una frase por función y devolverlas en el orden de extract_functions.
        Si hay error o no hay config, devolvemos [] para que el caller haga fallback.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    try:
        file_ext = "py" if language == "python" else ("js" if language == "javascript" else "")
        # Attempt to use the embedded minimizer prompt if present in package
        prompt_path = os.path.join(os.path.dirname(__file__), "llm", "prompts", "contextual_minimizer.md")
        system_prompt = prompt_path if os.path.exists(prompt_path) and os.path.isfile(prompt_path) else None
        if system_prompt:
            _ctx_log(f"contextual: using embedded minimizer prompt at {system_prompt}")
        docs = generate_docstrings_for_file(
            content,
            file_ext=file_ext,
            lang=doc_lang,
            level="llm+heuristic",   # intenta LLM, cae a heurística si no
            model_hint=model_hint,
            system_prompt=system_prompt,
        )
        # Construimos un mapa “nombre simple” -> primera línea del docstring
        name_to_one_liner = {}
        for key, text in (docs or {}).items():
            # key suele ser "module", "ClassName", "ClassName.method", "func"
            simple = key.rsplit(".", 1)[-1]
            name_to_one_liner[simple] = (_firstline(text) or "").strip()

        # Extraemos las funciones y las mapeamos
        funcs_py = extract_functions(content, "python") if language == "python" else []
        funcs_js = extract_functions(content, "javascript") if language == "javascript" else []
        funcs = funcs_py or funcs_js

        out = []
        for f in funcs:
            n = f.get("name") or ""
            out.append(name_to_one_liner.get(n, ""))  # vacío => fallback heurístico después
        return out
    except Exception as e:
        _ctx_log(f"contextual: LLM descriptions failed → {e!r}")
        return []

# Brief: minimize_content
def minimize_content(
    content: str,
    file_extension: str,
    level: str = "basic",
    *,
    docstrings_mode: str = "off",
    doc_lang: str = "en",
    provider: Optional[str] = None,
    file_path: Optional[str] = None,  # <-- ADDED
) -> str:

    lang_map = {
        "py": "python",
        "python": "python",
        "js": "javascript",
        "mjs": "javascript",
        "cjs": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "css": "css",
        "scss": "css",
        "less": "css",
        "html": "html",
        "htm": "html",
        "md": "markdown",
        "markdown": "markdown",
        "json": "json",
        "yml": "yaml",
        "yaml": "yaml",
        "toml": "toml",
    }
    language = lang_map.get(file_extension.lower(), "generic")
    if not content:
        return content

    if level == "docstrings":
        # Retained for compatibility; now contextual path can also generate
        if language == "python":
            # Old path produced comments, not true docstrings. Keep behavior for compatibility.
            # Prefer using contextual+--docstrings generate for the new flow.
            return _build_contextual_skeleton(extract_functions(content, "python"), [], "python", doc_mode=docstrings_mode)
        if language in ("javascript", "typescript"):
            return _build_contextual_skeleton(extract_functions(content, "javascript"), [], "javascript", doc_mode=docstrings_mode)
        return content

    if level == "contextual":
        language = "python" if file_extension in ("py", "pyw") else (
            "javascript" if file_extension in ("js", "jsx", "ts", "tsx") else None
        )
        if not language:
            _ctx_log(f"contextual: lang={file_extension} not supported → passthrough")
            return content

        llm_result: Optional[str] = None
        llm_err: Optional[Exception] = None
        settings: Dict[str, Any] = {}
        legacy_descs: Optional[List[str]] = None

        with _Spinner(f"LLM minimize ({file_extension})") as sp:
            try:
                sp.stage("contacting LLM")
                model_hint = os.getenv("COPYCLIP_LLM_MODEL")
                llm_payload = _run_coro_sync(
                    lambda: contextual_minimize(content, file_extension, doc_lang, model_hint, provider, file_path),
                    timeout_s=float(os.getenv("COPYCLIP_LLM_TIMEOUT", str(60)))
                )

                # Backward compatibility with old tests/mocks:
                # - new flow returns (result, err, settings)
                # - old flow/mocks may return list[str] descriptions or a plain string
                if isinstance(llm_payload, tuple) and len(llm_payload) == 3:
                    llm_result, llm_err, settings = llm_payload
                    if not isinstance(settings, dict):
                        settings = {}
                elif isinstance(llm_payload, list):
                    legacy_descs = [str(x) for x in llm_payload]
                elif isinstance(llm_payload, str):
                    llm_result = llm_payload

                sp.stage("post-processing")
            except Exception as e:
                llm_err = e
                sp.stage("LLM task failed")
            
            if llm_err:
                sp.fail("error")
            else:
                sp.success("done")

        if legacy_descs is not None:
            funcs = extract_functions(content, "python" if language == "python" else "javascript")
            return _build_contextual_skeleton(funcs, legacy_descs, language, doc_mode=docstrings_mode)

        if llm_result and len(llm_result.strip()) > 100:
            _ctx_dbg("contextual: LLM minimization successful")
            return llm_result

        if llm_err:
            # ---> THIS IS THE NEW LOGGING LOGIC <---
            logger = logging.getLogger(__name__)
            provider_name = "unknown"
            if isinstance(settings, dict):
                provider_name = settings.get("provider") or provider_name
            provider_name = provider_name if provider_name != "unknown" else (
                provider or os.getenv("COPYCLIP_LLM_PROVIDER") or "deepseek"
            )
            # NOTE: elapsed_ms is now correctly calculated and passed.
            elapsed_ms = int((time.time() - sp.start_time) * 1000) if hasattr(sp, 'start_time') else 0
            log_data = map_exception_to_log_data(
                exc=llm_err,
                provider=provider_name,
                attempt=1,  # Final attempt
                elapsed_ms=elapsed_ms,
                file_path=file_path,
            )
            message = f"minimization_failed: {log_data['cause']}"
            log_entry = {"message": message, **log_data}
            logger.error(json.dumps(log_entry))

            # User-facing actionable hint (single line) when possible.
            err_text = str(llm_err)
            if "api key not provided" in err_text.lower() or "missing api key" in err_text.lower():
                _ctx_log(f"LLM auth failed ({provider_name}): missing API key. Set provider key in .env")
            elif log_data.get("cause") == "timeout":
                _ctx_log(f"LLM timeout ({provider_name}). Try COPYCLIP_LLM_TIMEOUT=120")
            elif err_text:
                _ctx_log(f"LLM fallback reason ({provider_name}): {err_text}")
            # ---> END OF NEW LOGIC <---
        
        # Fallback: more detailed structural rendering (keeps imports, signatures, and optionally docstrings)
        if language == "python":
            return _python_render_intelligent(content, docstrings_mode, doc_lang)
        if language == "javascript":
            return _jsts_render_intelligent(content, file_extension, docstrings_mode, doc_lang)

        _ctx_log(f"contextual: lang={language} not supported → passthrough")
        return content

    if level == "structural":
        if language == "python":
            # very compact structure
            out_lines: List[str] = []
            for line in content.splitlines():
                m = re.match(r"^(\s*)(def|class)\s+[^\n:]+:", line)
                if m:
                    indent, kind = m.group(1), m.group(2)
                    out_lines.append(line.rstrip())
                    out_lines.append(indent + ("    pass" if kind == "def" else "    ..."))
            return ("\n".join(out_lines).rstrip() + "\n") if out_lines else (content.strip() + "\n")
        if language in ("javascript", "typescript"):
            out_lines: List[str] = []
            patterns = [
                re.compile(r"^\s*(export\s+)?(default\s+)?(async\s+)?function\s+[A-Za-z0-9_$]+\s*\(", re.M),
                re.compile(r"^\s*(export\s+)?(default\s+)?class\s+[A-Za-z0-9_$]+\s*(\{|$)", re.M),
                re.compile(r"^\s*(const|let|var)\s+[A-Za-z0-9_$]+\s*=\s*(async\s*)?\([^)]*\)\s*=>", re.M),
            ]
            for line in content.splitlines():
                if any(p.search(line) for p in patterns):
                    ln = line.rstrip()
                    if ln.endswith("{"):
                        out_lines.append(ln + " /* ... */ }")
                    else:
                        out_lines.append(ln)
            return ("\n".join(out_lines).rstrip() + "\n") if out_lines else (content.strip() + "\n")

    # basic/aggressive
    rules = MINIMIZATION_RULES.get(language, {})
    for rule_name in ("comments", "docstrings", "html_comments"):
        rule = rules.get(rule_name)
        if rule:
            content = rule.sub("", content)
    content = _collapse_blank_lines(content)

    if level == "aggressive":
        content = re.sub(r"\n\s*\n", "\n", content)
        if language == "python":
            content = re.sub(r"->\s*[A-Za-z0-9_\. \[\],|]+", "", content)
            content = re.sub(r"(\(|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*[^,)\n]+", r"\1 \2", content)
        if language in ("javascript", "typescript"):
            content = re.sub(r"\{\s*(?:.|\n){200,}?\}", "{/*...*/}", content)
            content = re.sub(r"\[\s*(?:.|\n){200,}?\]", "[/*...*/]", content)
    return content.strip() + "\n"

