# src/copyclip/docstrings.py
from __future__ import annotations

import asyncio
import os
import textwrap
import time
from typing import Dict, Iterable, List, Literal, Optional, Tuple

from .tokens import count_chat_tokens
from .ast_extractor import ContextRecord, ModuleContext, extract_python_context, extract_jsts_context
from .llm.config import load_config, resolve_settings
from .llm_client import LLMClientFactory

PROMPT_VERSION = "v1-2025-08-22"

# === Prompt Templates (embebidos, versión fija) ===

MODULE_PROMPT_SYSTEM = (
    "You are a precise technical writer generating module docstrings. "
    "You must be concise, accurate, and avoid speculation."
)

MODULE_PROMPT_USER = (
    'Project: CopyClip – Intelligent Directory Content Aggregator\n'
    'Task: Write a PEP-257 compliant module docstring that orients readers and LLMs.\n'
    'Module name: {module_name}\n'
    'Language: {lang}\n'
    'Constraints:\n'
    '- One-line summary first; then a short paragraph of context.\n'
    '- List main classes/functions exposed by the module (names only).\n'
    '- Mention side effects, I/O, or platform dependencies if applicable.\n'
    '- Avoid including code or secrets.\n'
    'Structured Context (no code bodies):\n'
    '- Public symbols: {public_symbol_names}\n'
    '- Key responsibilities: {inferred_responsibilities}\n'
    '- External deps (names only): {external_dependencies}\n'
)

SYMBOL_PROMPT_SYSTEM = (
    "You generate high-signal, PEP-257 compliant docstrings for code symbols using only structural context. "
    "Do not invent APIs that are not present. Be concise."
)

SYMBOL_PROMPT_USER = (
    'Goal: Produce a docstring for this {kind}.\n'
    'Module: {module_name}\n'
    'Symbol path: {symbol_path}\n'
    'Language: {lang}\n'
    'Structural Context (no code bodies):\n'
    '- Signature text: {signature_text}\n'
    '- Decorators: {decorator_names}\n'
    '- Async: {is_async}\n'
    '- Calls (names only): {called_names}\n'
    '- Uses (imports/consts names only): {referenced_names}\n'
    '- Raises (names): {raise_names}\n'
    '- Existing docstring (first line if any): {existing_firstline}\n'
    'Docstring requirements:\n'
    '- First line: crisp summary sentence.\n'
    '- Sections (only if relevant): Parameters, Returns, Raises, Side Effects, Notes, Examples.\n'
    '- Prefer short, descriptive parameter explanations based on names and usage hints.\n'
    '- Avoid speculative details; if uncertain, say “Implementation defined”.\n'
    'Output: raw docstring text (no fences).\n'
)
# Brief: _wrap
# Brief: _wrap

# Brief: _wrap
def _wrap(s: str) -> str:
    lines = []
    for p in s.splitlines():
        if not p.strip():
            lines.append("")
        else:
            lines.extend(textwrap.wrap(p, width=100))
    return "\n".join(lines).strip() + "\n"
# Brief: _firstline

# Brief: _firstline
def _firstline(doc: str) -> str:
    for ln in doc.splitlines():
        t = ln.strip()
        if t:
            return t
    return ""
# Brief: _heuristic_docstring

# Brief: _heuristic_docstring
def _heuristic_docstring(symbol: ContextRecord) -> str:
    """
    
        Produce a compact heuristic docstring using available structural info.
        Prefer explicit param types and return annotation when present on the ContextRecord.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    first = f"{'Async ' if symbol.is_async else ''}{symbol.kind.title()} `{symbol.name}`."
    parts: List[str] = [first]

    # Parameters: prefer param_types if available, else fall back to signature parsing
    params: List[str] = []
    if getattr(symbol, "param_types", None):
        for p in symbol.param_types:
            # param_types entries are like "name: annotation" already
            params.append(p)
    else:
        sig = symbol.signature_text or ""
        open_paren = sig.find("(")
        close_paren = sig.find(")", open_paren + 1)
        if open_paren != -1 and close_paren != -1 and close_paren > open_paren + 1:
            inside = sig[open_paren + 1 : close_paren]
            for tok in [t.strip() for t in inside.split(",") if t.strip()]:
                if tok.startswith("*"):
                    continue
                name = tok.split(":")[0].split("=")[0].strip()
                if name:
                    params.append(f"{name}: Any")

    if params:
        parts.append("")
        parts.append("Parameters")
        parts.append("----------")
        for p in params[:10]:
            parts.append(p)

    # Calls (if any) - helpful contextual signal
    if symbol.called_names:
        parts.append("")
        parts.append("Calls")
        parts.append("-----")
        for c in symbol.called_names[:12]:
            parts.append(f"- {c}")

    # Side effects (if detected)
    if getattr(symbol, "side_effects", None):
        parts.append("")
        parts.append("Side Effects")
        parts.append("------------")
        for s in symbol.side_effects:
            parts.append(f"- {s}")

    # Returns
    ret = "Any"
    if getattr(symbol, "return_annotation", None):
        ra = symbol.return_annotation.strip()
        if ra:
            ret = ra
    else:
        # try to parse from signature
        sig = symbol.signature_text or ""
        if "->" in sig:
            ret = sig.split("->", 1)[1].strip(" :)") or "Any"

    parts.append("")
    parts.append("Returns")
    parts.append("-------")
    parts.append(ret)

    # Raises
    if symbol.raise_names:
        parts.append("")
        parts.append("Raises")
        parts.append("------")
        for r in symbol.raise_names[:8]:
            parts.append(f"- {r}")

    return _wrap("\n".join(parts))
# Brief: DocstringCache

# Brief: DocstringCache
class DocstringCache:
    def __init__(self, max_items: int = 4096):
        self._max = max_items
        self._data: Dict[Tuple[str, str, str], str] = {}
        self._order: List[Tuple[str, str, str]] = []

    def get(self, file_sha: str, symbol_path: str) -> Optional[str]:
        key = (file_sha, symbol_path, PROMPT_VERSION)
        return self._data.get(key)

    def put(self, file_sha: str, symbol_path: str, text: str) -> None:
        key = (file_sha, symbol_path, PROMPT_VERSION)
        if key in self._data:
            self._data[key] = text
            return
        if len(self._data) >= self._max:
            old = self._order.pop(0)
            self._data.pop(old, None)
        self._data[key] = text
        self._order.append(key)

_CACHE = DocstringCache()
# Brief: _llm_batch_generate

# Brief: _llm_batch_generate
async def _llm_batch_generate(symbols: List[ContextRecord], lang: str, system_prompt: Optional[str] = None) -> List[str]:
    """
    
        Sends one symbol per request to keep the implementation simple & deterministic.
        Batching still happens at the call loop level respecting token budget.
    
        New parameter:
        - system_prompt: Optional[str] = None
          If provided, this may be either:
            * a filesystem path to a prompt file (the client will read it), or
            * a literal prompt string.
          The resolved prompt will be provided to the LLM client as the system-role message.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    cfg = load_config(os.getenv("COPYCLIP_LLM_CONFIG"))
    s = resolve_settings(cfg,
                         cli_provider=os.getenv("COPYCLIP_LLM_PROVIDER"),
                         cli_model=os.getenv("COPYCLIP_LLM_MODEL"),
                         cli_endpoint=os.getenv("COPYCLIP_LLM_ENDPOINT"),
                         cli_timeout=int(os.getenv("COPYCLIP_LLM_TIMEOUT", "0") or 20))
    client = LLMClientFactory.create(
        s["provider"], api_key=s.get("api_key"), model=s.get("model"),
        endpoint=s.get("endpoint"), timeout=int(s.get("timeout") or 20),
        extra_headers=s.get("extra_headers") or {}
    )

    import aiohttp  # ensured by client paths

    async def _ask(sym: ContextRecord) -> str:
        # We re-use the describe_functions pipe by embedding the whole symbol prompt as a "snippet".
        # Each call returns one line; here we request the complete docstring by passing the docstring
        # prompt as the "snippet" and instructing model to output it raw. This keeps tests offline.
        prompt_user = SYMBOL_PROMPT_USER.format(
            kind=sym.kind,
            module_name=sym.module_name,
            symbol_path=sym.symbol_path,
            lang=lang,
            signature_text=sym.signature_text,
            decorator_names=", ".join(sym.decorators) if sym.decorators else "none",
            is_async=str(sym.is_async),
            called_names=", ".join(sym.called_names) if sym.called_names else "none",
            referenced_names=", ".join(sym.referenced_names) if sym.referenced_names else "none",
            raise_names=", ".join(sym.raise_names) if sym.raise_names else "none",
            existing_firstline=(sym.existing_firstline or "none"),
        )
        # Fallback to heuristic if provider only returns short lines
        try:
            # Use the provider with a single "snippet"
            # Pass system_prompt through to the client so callers can inject a per-file prompt or prompt file path.
            lines = await client.describe_functions(
                [f"[SYSTEM]{SYMBOL_PROMPT_SYSTEM}\n[USER]\n{prompt_user}"], lang, system_prompt=system_prompt
            )
            txt = "\n".join(lines).strip()
            if len(txt.splitlines()) < 2:
                return _heuristic_docstring(sym)
            return _wrap(txt)
        except Exception:
            return _heuristic_docstring(sym)

    # naive rate limit: 5 req/s
    out: List[str] = []
    for i, sym in enumerate(symbols):
        out.append(await _ask(sym))
        if (i + 1) % 5 == 0:
            await asyncio.sleep(0.2)
    return out
# Brief: _batch_symbols_by_budget

# Brief: _batch_symbols_by_budget
def _batch_symbols_by_budget(symbols: List[ContextRecord], model_hint: Optional[str]) -> List[List[ContextRecord]]:
    # Deterministic batches by growing until ~2000 tokens per batch (rough)
    batches: List[List[ContextRecord]] = []
    current: List[ContextRecord] = []
    current_tokens = 0
    for sym in symbols:
        # estimate tokens from signature & names only
        t, _, _ = count_chat_tokens(
            f"{sym.signature_text} {', '.join(sym.called_names)} {', '.join(sym.referenced_names)}", model_hint
        )
        if current and current_tokens + t > 2000:
            batches.append(current)
            current = [sym]
            current_tokens = t
        else:
            current.append(sym)
            current_tokens += t
    if current:
        batches.append(current)
    return batches
# Brief: _module_docstring

# Brief: _module_docstring
def _module_docstring(mod: ModuleContext, lang: str, level: str) -> str:
    """
    
        Produce a compact PEP-257 module docstring focused on:
          - One-line summary
          - Public API (comma list)
          - Depends on: external deps (comma list)
        Avoid vague inferred responsibilities in the header; keep it factual.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    public_api = ", ".join(mod.public_symbol_names) or "none"
    depends = ", ".join(mod.external_dependencies) or "none"

    doc_lines = [
        f"{mod.module_name} module.",
        "",
        "Public API:",
        f"    {public_api}",
        "",
        "Depends on:",
        f"    {depends}",
    ]
    return _wrap("\n".join(doc_lines))
# Brief: generate_docstrings_for_file

# Brief: generate_docstrings_for_file
def generate_docstrings_for_file(
    content: str,
    *,
    file_ext: str = "py",
    lang: Literal["en", "es"] = "en",
    level: Literal["heuristic", "llm", "llm+heuristic"] = "heuristic",
    model_hint: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> Dict[str, str]:
    """
    
        Returns {symbol_path: docstring_text}, including module key as f"{mod.module_name}:__module__"
    
        New parameter:
        - system_prompt: Optional[str] = None
          If provided, may be a path to a prompt file or a literal prompt string. When provided and LLM
          generation is used, the prompt will be supplied to the LLM client as the system role message.
    Args:
        TODO: describe arguments
    """
    if file_ext.lower() in ("py", "python"):
        mod, symbols = extract_python_context(content)
    elif file_ext.lower() in ("js", "mjs", "cjs", "ts", "tsx"):
        mod, symbols = extract_jsts_context(content)
    else:
        return {}

    result: Dict[str, str] = {}

    # Module docstring
    mod_key = f"{mod.module_name}:__module__"
    cached = _CACHE.get(mod.file_sha256, mod_key)
    if cached:
        result[mod_key] = cached
    else:
        mdoc = _module_docstring(mod, lang, "heuristic" if level.startswith("llm") else level)
        _CACHE.put(mod.file_sha256, mod_key, mdoc)
        result[mod_key] = mdoc

    # Symbols
    # Cache lookups
    need: List[ContextRecord] = []
    for sym in symbols:
        cached = _CACHE.get(mod.file_sha256, sym.symbol_path)
        if cached:
            result[sym.symbol_path] = cached
        else:
            need.append(sym)

    if need:
        # Determine generation strategy
        if level == "heuristic":
            for sym in need:
                doc = _heuristic_docstring(sym)
                _CACHE.put(mod.file_sha256, sym.symbol_path, doc)
                result[sym.symbol_path] = doc
        else:
            # Offline-safe path: attempt LLM, fallback to heuristic
            batches = _batch_symbols_by_budget(need, model_hint)
            texts: List[str] = []
            try:
                async def _run():
                    outs: List[str] = []
                    for b in batches:
                        # Pass system_prompt down to the LLM batch generator
                        outs.extend(await _llm_batch_generate(b, lang, system_prompt=system_prompt))
                    return outs
                texts = asyncio.run(_run())
            except Exception:
                texts = [None] * sum(len(b) for b in batches)  # type: ignore

            i = 0
            for b in batches:
                for sym in b:
                    doc = texts[i] if texts and texts[i] else _heuristic_docstring(sym)
                    _CACHE.put(mod.file_sha256, sym.symbol_path, doc)
                    result[sym.symbol_path] = doc
                    i += 1

    return result
