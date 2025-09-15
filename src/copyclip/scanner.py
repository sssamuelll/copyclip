
# src/copyclip/scanner.py
import os
import fnmatch
import shutil
import logging
from typing import Callable, Iterable, List, Optional, Sequence, Set
from gitignore_parser import parse_gitignore
# Brief: is_python_shebang
# Brief: is_python_shebang

# Brief: is_python_shebang
def is_python_shebang(file_path: str) -> bool:
    """
    Checks if a file starts with a Python shebang.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            first_line = f.readline(100)  # Lee como máximo 100 caracteres
            return first_line.startswith("#!") and "python" in first_line
    except Exception:
        return False
# Brief: _normalize_path

# Brief: _normalize_path
def _normalize_path(path: str) -> str:
    """
    Normalize paths to use forward slashes for matching.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    return path.replace(os.sep, "/")

# Brief: _parse_csv_list

# Brief: _parse_csv_list
def _parse_csv_list(value: Optional[str]) -> List[str]:
    """
    
        Parse a comma-separated string into a clean list.
        Accepts None or already-a-list; trims spaces and drops empties.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
    else:
        parts = [str(p).strip() for p in value]  # type: ignore
    return [p for p in parts if p]

# Brief: _normalize_exts

# Brief: _normalize_exts
def _normalize_exts(extensions: Optional[Sequence[str]], extension: Optional[str]) -> Set[str]:
    """
    
        Combine legacy single 'extension' and new 'extensions' into a normalized set.
        Accepts with or without leading dots; enforces lower-case.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    exts: Set[str] = set()
    for e in _parse_csv_list(extension) + list(_parse_csv_list(extensions)):  # type: ignore
        if not e:
            continue
        e = e.lower()
        if not e.startswith("."):
            e = "." + e
        exts.add(e)
    return exts

# Brief: _compose_ignore_predicate

# Brief: _compose_ignore_predicate
def _compose_ignore_predicate(base_path: str, ignore_file_path: Optional[str]) -> Callable[[str], bool]:
    """
    
        Build a predicate that returns True if a relative path should be ignored,
        combining .copyclipignore and .gitignore if present.
        Precedence:
          1) explicit ignore_file_path, if it exists
          2) base_path/.copyclipignore
          3) base_path/.gitignore
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    predicates: List[Callable[[str], bool]] = []
    logger = logging.getLogger("copyclip")

    def try_add(path: str) -> None:
        if os.path.exists(path):
            # Always attempt to add the robust fnmatch-based predicate derived
            # from the ignore file contents. This handles simple ignore lines
            # reliably without depending on external parser behavior.
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    raw_lines = [ln.strip() for ln in fh.readlines()]
                patterns = [ln for ln in raw_lines if ln and not ln.startswith("#")]
                if patterns:
                    predicates.append(lambda rel, pats=patterns: _matches_any(pats, rel))
                    logger.info("Loaded ignore patterns from: %s (base_dir=%s)", path, base_path)
            except Exception as e:
                logger.warning("Failed to read ignore file %s: %s", path, e)

            # Try to add gitignore_parser predicate as an additional, more
            # complete option if available. Don't fail if it raises.
            try:
                predicates.append(parse_gitignore(path, base_dir=base_path))
                logger.info("Loaded ignore file (gitignore_parser): %s (base_dir=%s)", path, base_path)
            except Exception as e:
                logger.debug("gitignore_parser could not parse %s: %s", path, e)

    if ignore_file_path and os.path.exists(ignore_file_path):
        try_add(ignore_file_path)
    else:
        try_add(os.path.join(base_path, ".copyclipignore"))
        try_add(os.path.join(base_path, ".gitignore"))

    if not predicates:
        logger.info("No ignore files loaded for base_dir=%s", base_path)
        return lambda rel: False

    def is_ignored(rel: str) -> bool:
        # Check both file and directory semantics
        norm = _normalize_path(rel)
        for pred in predicates:
            try:
                if pred(norm) or pred(norm + "/"):
                    return True
            except Exception:
                # Defensive: never fail scanning due to ignore predicate
                continue
        return False

    return is_ignored

# Brief: _matches_any

# Brief: _matches_any
def _matches_any(patterns: Iterable[str], rel: str) -> bool:
    """
    Return True if rel matches any of the provided glob patterns.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    if not patterns:
        return False
    rel_norm = _normalize_path(rel)
    for pat in patterns:
        pat = pat.strip()
        if not pat:
            continue
        # Support simple path-prefix matches by augmenting with '/**'
        if not any(ch in pat for ch in ["*", "?", "["]):
            prefix = pat.rstrip("/")
            if rel_norm == prefix or rel_norm.startswith(prefix + "/"):
                return True
        if fnmatch.fnmatch(rel_norm, pat):
            return True
    return False

# Brief: scan_files

# Brief: scan_files
def scan_files(
    base_path: str,
    ignore_file_path: Optional[str] = None,
    extension: Optional[str] = None,
    *,
    extensions: Optional[Sequence[str]] = None,
    include: Optional[Sequence[str]] = None,
    exclude: Optional[Sequence[str]] = None,
    only: Optional[Sequence[str]] = None,
    max_file_size: Optional[int] = None,
    follow_symlinks: bool = False,
) -> List[str]:
    """
    Scan directory tree in a single pass and return file paths to process.

    Args:
        base_path: Root directory to scan
        ignore_file_path: Optional path to ignore file (legacy; see precedence rules)
        extension: Single extension to include (legacy; e.g. '.py' or 'py')
        extensions: List/comma-separated extensions to include ('.py,.ts,.md')
        include: Glob patterns to include (in addition to extensions)
        exclude: Glob patterns to exclude
        only: Restrict scan to these subpaths/patterns (acts like include roots)
        max_file_size: Skip files larger than this (in bytes)
        follow_symlinks: Whether to follow symlinks during traversal
    Returns:
        List of absolute file paths
    """
    is_ignored = _compose_ignore_predicate(base_path, ignore_file_path)
    exts = _normalize_exts(extensions, extension)
    include = _parse_csv_list(include)
    exclude = _parse_csv_list(exclude)
    only = _parse_csv_list(only)

    all_files: List[str] = []
    print("[INFO] Scanning directory tree...")

    # Choose correct walk signature depending on Python version
    walk_kwargs = {"followlinks": follow_symlinks}

    for root, dirs, files in os.walk(base_path, **walk_kwargs):  # type: ignore[arg-type]
        # Prune ignored directories for performance
        pruned: List[str] = []
        for d in list(dirs):
            rel_dir = os.path.relpath(os.path.join(root, d), base_path)
            if is_ignored(rel_dir):
                pruned.append(d)
        for d in pruned:
            dirs.remove(d)

        for file_name in files:
            absolute_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(absolute_path, base_path)

            # Ignore rule
            if is_ignored(relative_path):
                continue

            # Extension filter (if any)
            if exts:
                _, dot, ext = file_name.rpartition(".")
                curr_ext = f".{ext.lower()}" if dot else ""

                # Comprueba si el archivo coincide con los filtros
                is_match = False
                if curr_ext in exts:
                    is_match = True
                # Si no tiene extensión, pero se buscan archivos .py, revisa el shebang
                elif curr_ext == "" and ".py" in exts:
                    if is_python_shebang(absolute_path):
                        is_match = True
                
                if not is_match:
                    continue

            # 'only' roots (restrict to specific subtrees/patterns)
            if only and not _matches_any(only, relative_path):
                continue

            # 'include' globs (if provided, must match at least one)
            if include and not _matches_any(include, relative_path):
                continue

            # 'exclude' globs
            if exclude and _matches_any(exclude, relative_path):
                continue

            # Max file size (per-file)
            if max_file_size is not None:
                try:
                    if os.path.getsize(absolute_path) > max_file_size:
                        continue
                except OSError:
                    # If size cannot be read, skip conservatively
                    continue

            all_files.append(absolute_path)

    print(f"[INFO] Found {len(all_files)} files to process")
    return all_files