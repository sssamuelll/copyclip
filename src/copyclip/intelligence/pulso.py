"""Pulso — the honest burst-recency atom ("Last contact").

The wedge is keeping the human connected to their intention across AI bursts.
The only LIVE trace of a burst is the Co-Authored-By trailer (git-blame author is
dead here — the human commits the AI's work under his own name). So Pulso reads
`commits.ai_attributed` (set at ingest, PR-P1), never the blame column.

What this proves, and nothing more: *an AI burst last shaped this file N days ago
and a human has not touched it since.* It measures elapsed time and recency. It
does NOT measure comprehension — a timestamp cannot witness understanding. When
there is no burst, or the human has already returned, Pulso is silent (None),
never a reassuring zero.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_git_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    s = value.strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _last_ratified_decision(conn, project_id: int, path: str) -> datetime | None:
    """The most recent time the human RATIFIED a decision directly linked to this
    file — the strongest witness act the cuaderno records (an authoring write over
    the human's own ledger, already timestamped). 'status_change' is the human's
    PATCH (DecisionConfirm); 'created'/'ref_added'/'link_added' are system writes.
    Only DIRECT decision_refs (ref_type='file') count — never decision_links globs,
    which are fuzzy and would overclaim the file edge. Witnesses review, not
    comprehension."""
    row = conn.execute(
        """
        SELECT MAX(dh.created_at)
        FROM decision_history dh
        JOIN decisions d ON d.id = dh.decision_id
        JOIN decision_refs dr ON dr.decision_id = d.id AND dr.ref_type = 'file' AND dr.ref_value = ?
        WHERE d.project_id = ? AND dh.action = 'status_change'
        """,
        (path, project_id),
    ).fetchone()
    return _parse_git_iso(row[0]) if row and row[0] else None


def build_last_contact(
    conn, project_id: int, path: str, *, now: datetime | None = None
) -> dict[str, Any] | None:
    """Return the Last-contact reading for a file, or None when there is nothing
    honest to report (no AI burst, or the human already returned).

    Keys: last_contact_days (days since the human's last touch, or since the
    burst if never), ai_burst_days (days since the most recent AI burst),
    never_human_touched (the human has no commit on this file).
    """
    now = now or datetime.now(timezone.utc)

    rows = conn.execute(
        """
        SELECT c.date, c.ai_attributed
        FROM file_changes fc
        JOIN commits c ON c.sha = fc.commit_sha
        WHERE fc.project_id = ? AND fc.file_path = ?
        """,
        (project_id, path),
    ).fetchall()

    last_ai: datetime | None = None
    last_human: datetime | None = None
    for date_str, ai_attributed in rows:
        dt = _parse_git_iso(date_str)
        if dt is None:
            continue
        if ai_attributed:
            if last_ai is None or dt > last_ai:
                last_ai = dt
        else:
            if last_human is None or dt > last_human:
                last_human = dt

    # No burst ever shaped this file -> nothing to track. Absence, not zero.
    if last_ai is None:
        return None

    # v0.2: the human "returns" to a file via a commit OR a ratified decision (the
    # strongest cuaderno witness). Take the later of the two as the contact event;
    # on a tie, prefer the ratification (the firmer, authoring act).
    last_review = _last_ratified_decision(conn, project_id, path)
    last_return: datetime | None = None
    source: str | None = None
    if last_human is not None:
        last_return, source = last_human, "git"
    if last_review is not None and (last_return is None or last_review >= last_return):
        last_return, source = last_review, "decision"

    # The human already returned since the most recent burst -> current, silent.
    if last_return is not None and last_return >= last_ai:
        return None

    def days_since(dt: datetime) -> int:
        return max(0, (now - dt).days)

    contact_anchor = last_return if last_return is not None else last_ai
    return {
        "last_contact_days": days_since(contact_anchor),
        "ai_burst_days": days_since(last_ai),
        # 'git' (a commit) | 'decision' (a ratified decision) | None (never returned;
        # gap measured since the burst). This proves return/review, never comprehension.
        "last_contact_source": source,
        "reviewed_days": days_since(last_review) if last_review is not None else None,
        "never_human_touched": last_human is None,
    }


def build_entry_cue(
    conn,
    project_id: int,
    *,
    now: datetime | None = None,
    stale_after_days: int = 14,
) -> dict[str, Any] | None:
    """The cuaderno's entry cue: the single most-overdue AI burst the human has
    NOT returned to — the proactive launching point into re-deriving it. Returns
    None (silent) when there is nothing honest to surface.

    Honest by construction:
    - The persisted `pulso_last_contact_days` only SELECTS candidates; the LIVE
      `build_last_contact` verdict DECIDES. A file the human came back to (live
      None) is dropped even if its snapshot still shows a positive gap — so the
      cue never fires on a file the human revisited.
    - It scopes its claim to the snapshot's age: `analyzed_age_days` is the age of
      `analysis_file_insights.updated_at`, and `stale` flags a snapshot older than
      `stale_after_days`. Past that line the surface should hedge ("as of the last
      analysis N days ago") rather than assert a present-tense gap it cannot
      witness. A missing `updated_at` never over-claims staleness.

    The FILE is stale, never the mind: recency plus a launch, never comprehension.
    """
    now = now or datetime.now(timezone.utc)

    rows = conn.execute(
        "SELECT path, updated_at FROM analysis_file_insights "
        "WHERE project_id=? AND pulso_last_contact_days IS NOT NULL",
        (project_id,),
    ).fetchall()

    candidates: list[tuple[str, str | None, dict[str, Any]]] = []
    for path, updated_at in rows:
        detail = build_last_contact(conn, project_id, path, now=now)
        if detail is None:
            continue  # human already returned / no burst — not hasn't-been-back
        candidates.append((path, updated_at, detail))

    if not candidates:
        return None

    # Most overdue first; ties broken by path for determinism.
    candidates.sort(key=lambda c: (-c[2]["last_contact_days"], c[0]))
    path, updated_at, detail = candidates[0]

    parsed = _parse_git_iso(updated_at)
    analyzed_age_days = max(0, (now - parsed).days) if parsed is not None else None
    stale = analyzed_age_days is not None and analyzed_age_days > stale_after_days

    return {
        "file_path": path,
        "last_contact_days": detail["last_contact_days"],
        "ai_burst_days": detail["ai_burst_days"],
        "last_contact_source": detail["last_contact_source"],
        "never_human_touched": detail["never_human_touched"],
        "analyzed_age_days": analyzed_age_days,
        "stale": stale,
    }
