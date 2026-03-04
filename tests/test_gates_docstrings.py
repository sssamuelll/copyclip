# tests/test_gates_docstrings.py
# Minimal deterministic tests to enforce documentation/gate rules.

import ast
import os
import re
from pathlib import Path
from typing import List

import pytest

SRC = Path("src/copyclip")
PY_FILES = list(SRC.rglob("*.py"))

# Strict style gates are opt-in; default local/dev runs should validate behavior,
# while these source-style checks run in dedicated quality pipelines.
if os.getenv("COPYCLIP_STRICT_GATES", "0") != "1":
    pytest.skip("Strict docstring/style gates disabled (set COPYCLIP_STRICT_GATES=1 to enable)", allow_module_level=True)

def _source_lines(path: Path) -> List[str]:
    return path.read_text(encoding="utf8").splitlines()

def _has_one_line_comment_above(lines: List[str], lineno: int) -> bool:
    # lineno is 1-based line number of def/class
    if lineno <= 1:
        return False
    prev = lines[lineno - 2].strip()
    return prev.startswith("#") and len(prev) > 1

def _doc_has_section(doc: str, section: str) -> bool:
    if not doc:
        return False
    return bool(re.search(r"^\s*" + re.escape(section) + r"\b", doc, re.M))

def test_one_line_comment_above_defs_and_classes():
    errs = []
    for p in PY_FILES:
        src = p.read_text(encoding="utf8")
        try:
            tree = ast.parse(src)
        except Exception as e:
            errs.append(f"{p}: parse error: {e}")
            continue
        lines = _source_lines(p)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not _has_one_line_comment_above(lines, node.lineno):
                    errs.append(f"{p}: missing one-line comment above {type(node).__name__} at {node.lineno}")
    assert not errs, "\n".join(errs)

def test_docstrings_have_args_and_returns_where_applicable():
    errs = []
    for p in PY_FILES:
        src = p.read_text(encoding="utf8")
        try:
            tree = ast.parse(src)
        except Exception as e:
            errs.append(f"{p}: parse error: {e}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                has_args = bool(getattr(node.args, "args", []))
                has_return = getattr(node, "returns", None) is not None
                if has_args and doc and not _doc_has_section(doc, "Args"):
                    errs.append(f"{p}: function at {node.lineno} docstring missing 'Args' section")
                if has_return and doc and not _doc_has_section(doc, "Returns"):
                    errs.append(f"{p}: function at {node.lineno} docstring missing 'Returns' section")
    assert not errs, "\n".join(errs)

def test_no_bare_pass():
    errs = []
    for p in PY_FILES:
        text = p.read_text(encoding="utf8")
        for m in re.finditer(r"^\s*pass\s*$", text, re.M):
            lineno = text[:m.start()].count("\n") + 1
            errs.append(f"{p}: bare pass at line {lineno}")
    assert not errs, "\n".join(errs)

def test_mermaid_block_presence_for_large_modules():
    errs = []
    for p in PY_FILES:
        src = p.read_text(encoding="utf8")
        try:
            tree = ast.parse(src)
        except Exception as e:
            errs.append(f"{p}: parse error: {e}")
            continue
        top_symbols = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        if len(top_symbols) >= 3:
            # require a mermaid block (text containing "graph TD;" in source)
            if "graph TD;" not in src:
                errs.append(f"{p}: expected mermaid block for module with {len(top_symbols)} symbols")
    assert not errs, "\n".join(errs)