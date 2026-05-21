"""External memory recap for Reacquaintance Mode.

Pulls a project-scoped recap from the locally-installed MemPalace CLI
(`mempalace wake-up --wing <wing>`) and parses it into a structured
list of decisions, sessions, and diary entries from outside the repo.

This complements the git/decisions evidence already in Reacquaintance:
git tells you *what* changed; this layer surfaces *why* — the
conversational context where the changes were planned and justified.

Gracefully degrades to ``available: False`` when MemPalace is not
installed or the call fails, so the briefing still works without it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timezone


SOURCE_TOOL = "mempalace"

_L1_HEADER = "## L1"
_LEVEL_HEADER = re.compile(r"^##\s+L\d+\b")
_CATEGORY = re.compile(r"^\[([^\[\]]+)\]$")
_TITLE_BODY_SPLIT = re.compile(r"^(.*?)\s{2,}(.+)$")
_ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")

_KIND_MAP = {
    "decisions": "decision",
    "agents": "agent",
    "diary": "diary",
    "general": "general",
    "documentation": "documentation",
    "planning": "planning",
    "src": "code",
    "cli": "code",
    "frontend": "code",
    "scripts": "code",
    "backend": "code",
    "tests": "code",
    "testing": "code",
    "code": "code",
    "problems": "problem",
    "fixes-applied": "fix",
    "design": "design",
    "brainstorm": "brainstorm",
    "brainstorms": "brainstorm",
    "decisions-pending": "decision",
}


def build_mempalace_recap(
    project_root: str,
    project_name: str,
    since_iso: str | None = None,
    wing: str | None = None,
    *,
    timeout_seconds: float = 10.0,
) -> dict:
    """Return a structured recap of external memory for the project.

    The result is always a dict so callers can render uniformly. When
    MemPalace is unavailable the ``available`` flag is ``False`` and
    ``items`` is empty.

    Args:
        project_root: absolute path to the project (currently unused but
            kept for parity with the rest of the intelligence API and to
            anchor future per-project wing overrides).
        project_name: name used to derive the default wing.
        since_iso: optional ISO-8601 timestamp; items whose parsed
            ``occurred_at`` is strictly older are dropped. Items without
            a parseable date are kept.
        wing: optional explicit wing name. Defaults to ``project_name``.
        timeout_seconds: subprocess timeout for ``mempalace wake-up``.
    """
    del project_root  # reserved for future per-project wing overrides

    effective_wing = (wing or project_name or "").strip()
    base = {
        "available": False,
        "source_tool": SOURCE_TOOL,
        "source_version": None,
        "wing": effective_wing or None,
        "since": since_iso,
        "items": [],
        "notes": [],
    }

    if not effective_wing:
        base["notes"].append("No wing resolved; skipped MemPalace recap.")
        return base

    if shutil.which(SOURCE_TOOL) is None:
        base["notes"].append("mempalace CLI not found on PATH.")
        return base

    raw, run_note = _run_wake_up(effective_wing, timeout_seconds=timeout_seconds)
    if raw is None:
        base["notes"].append(run_note or "MemPalace wake-up failed.")
        return base

    parsed = _parse_wake_up_output(raw)
    filtered, filter_note = _filter_by_since(parsed, since_iso)

    base["available"] = True
    base["source_version"] = _detect_version()
    base["items"] = filtered
    if filter_note:
        base["notes"].append(filter_note)
    if not filtered:
        if since_iso:
            base["notes"].append(
                "No external memory items newer than the previous visit."
            )
        else:
            base["notes"].append("Wing returned no items in L1.")

    return base


def _run_wake_up(wing: str, *, timeout_seconds: float) -> tuple[str | None, str | None]:
    try:
        result = subprocess.run(
            [SOURCE_TOOL, "wake-up", "--wing", wing],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return None, "mempalace CLI not found on PATH."
    except subprocess.TimeoutExpired:
        return None, f"mempalace wake-up timed out after {timeout_seconds:.0f}s."
    except OSError as exc:
        return None, f"mempalace wake-up failed: {exc}."

    if result.returncode != 0:
        stderr = (result.stderr or "").strip().splitlines()
        tail = stderr[-1] if stderr else f"exit {result.returncode}"
        return None, f"mempalace wake-up returned non-zero: {tail}"
    if not (result.stdout or "").strip():
        return None, "mempalace wake-up returned empty output."
    return result.stdout, None


def _detect_version() -> str | None:
    try:
        result = subprocess.run(
            [SOURCE_TOOL, "--version"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    text = (result.stdout or result.stderr or "").strip()
    match = re.search(r"(\d+\.\d+\.\d+)", text)
    return match.group(1) if match else (text or None)


def _parse_wake_up_output(text: str) -> list[dict]:
    items: list[dict] = []
    current_category: str | None = None
    in_l1 = False

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith(_L1_HEADER):
            in_l1 = True
            current_category = None
            continue
        if _LEVEL_HEADER.match(stripped) and not stripped.startswith(_L1_HEADER):
            in_l1 = False
            current_category = None
            continue

        if not in_l1:
            continue

        category_match = _CATEGORY.match(stripped)
        if category_match:
            current_category = category_match.group(1).strip()
            continue

        if stripped.startswith("- "):
            content = stripped[2:].strip()
            item = _parse_item(content, current_category)
            if item is not None:
                items.append(item)

    return items


def _parse_item(content: str, category: str | None) -> dict | None:
    content = content.strip()
    if not content:
        return None

    ref: str | None = None
    if content.endswith(")"):
        bracket_start = content.rfind("(")
        if bracket_start > 0:
            candidate = content[bracket_start + 1 : -1].strip()
            if candidate:
                ref = candidate
                content = content[:bracket_start].strip()

    match = _TITLE_BODY_SPLIT.match(content)
    if match:
        title = match.group(1).strip()
        body = match.group(2).strip()
    else:
        title, body = content, ""

    occurred_at: str | None = None
    if ref:
        date_match = _ISO_DATE.search(ref)
        if date_match:
            occurred_at = date_match.group(1)
    if occurred_at is None and body:
        date_match = _ISO_DATE.search(body)
        if date_match:
            occurred_at = date_match.group(1)

    return {
        "kind": _normalize_kind(category),
        "category": category,
        "title": title,
        "body": body,
        "ref": ref,
        "occurred_at": occurred_at,
    }


def _normalize_kind(category: str | None) -> str:
    if not category:
        return "other"
    return _KIND_MAP.get(category.lower(), category.lower())


def _filter_by_since(items: list[dict], since_iso: str | None) -> tuple[list[dict], str | None]:
    if not since_iso:
        return items, None

    cutoff = _parse_iso(since_iso)
    if cutoff is None:
        return items, "Ignored unparseable since_iso; returned all items."

    kept: list[dict] = []
    dropped = 0
    cutoff_date = cutoff.date()
    for item in items:
        item_date = _parse_date(item.get("occurred_at"))
        if item_date is None:
            kept.append(item)
            continue
        if item_date >= cutoff_date:
            kept.append(item)
        else:
            dropped += 1

    note = f"Filtered {dropped} item(s) older than {cutoff_date.isoformat()}." if dropped else None
    return kept, note


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
