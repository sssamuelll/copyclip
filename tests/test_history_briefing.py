"""Tests for the MemPalace-backed external memory recap.

Subprocess is monkeypatched so these tests do not depend on a real
``mempalace`` CLI being installed on the test runner.
"""
from __future__ import annotations

import subprocess

import pytest

from copyclip.intelligence import history_briefing
from copyclip.intelligence.history_briefing import (
    _filter_by_since,
    _parse_item,
    _parse_wake_up_output,
    build_mempalace_recap,
)


SAMPLE_WAKE_UP = """Wake-up text (~627 tokens):
==================================================
## L0 — IDENTITY
No identity configured. Create ~/.mempalace/identity.txt

## L1 — ESSENTIAL STORY

[agents]
  - Hermes agent pattern and stopping point (copyclip handoff epic)  User has a remote Claude Code agent named "Hermes" that executes multi-issue plans in copyclip using subagent-driven-development. Pa...  (session-2026-04-19-hermes-handoff)

[decisions]
  - Key design decisions for Handoff post-change review summaries (#45, PR #65)  Decision conflict rule: A touched file triggers a decision_conflict if the file is linked to any decision AND the file i...  (session-2026-04-20-issue-45)
  - Cognitive Debt contract (#47, PR #68 merged as daacb16) — first slice of epic #19.  Contract objects: debt_score (scalar [0,100] + severity label), debt_factor_breakdown (ordered list of per-factor...  (session-2026-04-20-issue-47)
  - Cognitive Debt Navigator UI (#50, PR #71 merged as 3b7cf8b).  New page: frontend/src/pages/DebtNavigatorPage.tsx wired under the Consciousness sidebar group with id "debt-navigator".  Layout: two-c...  (session-2026-04-20-issue-50)
  - Safe Agent Handoff epic (#18) CLOSED on 2026-04-20. All 7 child tasks merged in sequence across 3 sessions.  Final slice...  (session-2026-04-20-issue-46-epic-close)

## L2 — DETAILED CONTEXT
This section should be ignored.
"""


class _FakeCompleted:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _stub_run(stdout: str = "", stderr: str = "", returncode: int = 0):
    def _runner(cmd, **kwargs):
        return _FakeCompleted(stdout=stdout, stderr=stderr, returncode=returncode)

    return _runner


def _force_cli_present(monkeypatch):
    monkeypatch.setattr(history_briefing.shutil, "which", lambda _name: "/usr/local/bin/mempalace")


# ---------------------------------------------------------------------------
# Parser tests — operate on captured output, no subprocess involved.
# ---------------------------------------------------------------------------


def test_parser_extracts_items_from_l1_only():
    items = _parse_wake_up_output(SAMPLE_WAKE_UP)

    assert len(items) == 5
    assert all(item["title"] for item in items)
    assert not any("ignored" in item["body"].lower() for item in items)


def test_parser_categorizes_items_by_section():
    items = _parse_wake_up_output(SAMPLE_WAKE_UP)
    by_kind = {item["title"]: item["kind"] for item in items}

    assert by_kind["Hermes agent pattern and stopping point (copyclip handoff epic)"] == "agent"
    for title in by_kind:
        if title.startswith("Cognitive Debt") or title.startswith("Safe Agent") or title.startswith("Key design"):
            assert by_kind[title] == "decision"


def test_parser_extracts_ref_and_date():
    items = _parse_wake_up_output(SAMPLE_WAKE_UP)
    refs = {item["ref"] for item in items}
    dates = {item["occurred_at"] for item in items if item["occurred_at"]}

    assert "session-2026-04-20-issue-47" in refs
    assert "2026-04-19" in dates
    assert "2026-04-20" in dates


def test_parser_separates_title_from_body_on_double_space():
    items = _parse_wake_up_output(SAMPLE_WAKE_UP)
    by_title = {item["title"]: item for item in items}

    target = by_title["Cognitive Debt contract (#47, PR #68 merged as daacb16) — first slice of epic #19."]
    assert target["body"].startswith("Contract objects:")
    assert "(session-" not in target["body"]


def test_parser_handles_inline_parens_in_title():
    item = _parse_item(
        "Hermes agent pattern and stopping point (copyclip handoff epic)  body here  (session-2026-04-19-hermes)",
        "agents",
    )
    assert item is not None
    assert item["title"] == "Hermes agent pattern and stopping point (copyclip handoff epic)"
    assert item["body"] == "body here"
    assert item["ref"] == "session-2026-04-19-hermes"


def test_parser_handles_item_without_ref():
    item = _parse_item("Plain title only", "general")
    assert item is not None
    assert item["title"] == "Plain title only"
    assert item["body"] == ""
    assert item["ref"] is None
    assert item["occurred_at"] is None


def test_parser_returns_empty_for_blank_body():
    assert _parse_item("", "general") is None


def test_parser_ignores_content_outside_l1():
    text = """## L0 — IDENTITY
[ignored]
  - this should not be picked up  body  (ignored-ref)
"""
    items = _parse_wake_up_output(text)
    assert items == []


# ---------------------------------------------------------------------------
# since_iso filter tests
# ---------------------------------------------------------------------------


def test_filter_by_since_drops_older_items():
    items = [
        {"title": "old", "occurred_at": "2026-04-01"},
        {"title": "new", "occurred_at": "2026-04-20"},
        {"title": "boundary", "occurred_at": "2026-04-15"},
    ]
    kept, note = _filter_by_since(items, "2026-04-15T00:00:00Z")
    titles = {item["title"] for item in kept}

    assert titles == {"new", "boundary"}
    assert note is not None and "1 item" in note


def test_filter_by_since_keeps_items_without_date():
    items = [
        {"title": "no_date", "occurred_at": None},
        {"title": "old", "occurred_at": "2026-04-01"},
    ]
    kept, _note = _filter_by_since(items, "2026-04-15T00:00:00Z")
    titles = {item["title"] for item in kept}
    assert "no_date" in titles
    assert "old" not in titles


def test_filter_by_since_returns_all_when_no_cutoff():
    items = [{"title": "a", "occurred_at": "2026-04-01"}]
    kept, note = _filter_by_since(items, None)
    assert kept == items
    assert note is None


def test_filter_by_since_handles_invalid_iso():
    items = [{"title": "a", "occurred_at": "2026-04-01"}]
    kept, note = _filter_by_since(items, "not-a-date")
    assert kept == items
    assert note is not None and "unparseable" in note


# ---------------------------------------------------------------------------
# build_mempalace_recap orchestration tests
# ---------------------------------------------------------------------------


def test_recap_returns_unavailable_when_cli_missing(monkeypatch):
    monkeypatch.setattr(history_briefing.shutil, "which", lambda _name: None)

    recap = build_mempalace_recap("/tmp/proj", "copyclip")

    assert recap["available"] is False
    assert recap["items"] == []
    assert recap["source_tool"] == "mempalace"
    assert any("not found" in note.lower() for note in recap["notes"])


def test_recap_returns_unavailable_on_subprocess_filenotfound(monkeypatch):
    _force_cli_present(monkeypatch)

    def _raise(*_args, **_kwargs):
        raise FileNotFoundError("mempalace")

    monkeypatch.setattr(history_briefing.subprocess, "run", _raise)

    recap = build_mempalace_recap("/tmp/proj", "copyclip")
    assert recap["available"] is False
    assert any("not found" in note.lower() for note in recap["notes"])


def test_recap_returns_unavailable_on_timeout(monkeypatch):
    _force_cli_present(monkeypatch)

    def _raise(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="mempalace", timeout=10.0)

    monkeypatch.setattr(history_briefing.subprocess, "run", _raise)

    recap = build_mempalace_recap("/tmp/proj", "copyclip", timeout_seconds=10.0)
    assert recap["available"] is False
    assert any("timed out" in note.lower() for note in recap["notes"])


def test_recap_returns_unavailable_on_nonzero_exit(monkeypatch):
    _force_cli_present(monkeypatch)
    monkeypatch.setattr(history_briefing.subprocess, "run", _stub_run(stdout="", stderr="boom", returncode=2))

    recap = build_mempalace_recap("/tmp/proj", "copyclip")
    assert recap["available"] is False
    assert any("non-zero" in note for note in recap["notes"])


def test_recap_returns_unavailable_on_empty_output(monkeypatch):
    _force_cli_present(monkeypatch)
    monkeypatch.setattr(history_briefing.subprocess, "run", _stub_run(stdout="   \n", returncode=0))

    recap = build_mempalace_recap("/tmp/proj", "copyclip")
    assert recap["available"] is False
    assert any("empty" in note.lower() for note in recap["notes"])


def test_recap_returns_unavailable_when_no_wing_resolvable(monkeypatch):
    _force_cli_present(monkeypatch)

    recap = build_mempalace_recap("/tmp/proj", "")
    assert recap["available"] is False
    assert recap["wing"] is None


def test_recap_parses_full_output_when_available(monkeypatch):
    _force_cli_present(monkeypatch)
    monkeypatch.setattr(history_briefing.subprocess, "run", _stub_run(stdout=SAMPLE_WAKE_UP, returncode=0))

    recap = build_mempalace_recap("/tmp/proj", "copyclip")

    assert recap["available"] is True
    assert recap["wing"] == "copyclip"
    assert len(recap["items"]) == 5
    kinds = {item["kind"] for item in recap["items"]}
    assert "agent" in kinds and "decision" in kinds


def test_recap_filters_by_since_when_provided(monkeypatch):
    _force_cli_present(monkeypatch)
    monkeypatch.setattr(history_briefing.subprocess, "run", _stub_run(stdout=SAMPLE_WAKE_UP, returncode=0))

    recap = build_mempalace_recap("/tmp/proj", "copyclip", since_iso="2026-04-20T00:00:00Z")

    assert recap["available"] is True
    titles = {item["title"] for item in recap["items"]}
    assert not any("Hermes agent pattern" in t for t in titles)
    assert any("Cognitive Debt" in t for t in titles)


def test_recap_uses_explicit_wing_over_project_name(monkeypatch):
    _force_cli_present(monkeypatch)
    calls: list[list[str]] = []

    def _runner(cmd, **_kwargs):
        calls.append(list(cmd))
        if "wake-up" in cmd:
            return _FakeCompleted(stdout=SAMPLE_WAKE_UP, returncode=0)
        return _FakeCompleted(stdout="MemPalace 3.3.4", returncode=0)

    monkeypatch.setattr(history_briefing.subprocess, "run", _runner)

    build_mempalace_recap("/tmp/proj", "copyclip", wing="custom_wing")

    wake_calls = [c for c in calls if "wake-up" in c]
    assert wake_calls, "expected at least one wake-up subprocess call"
    assert wake_calls[0] == ["mempalace", "wake-up", "--wing", "custom_wing"]


@pytest.mark.parametrize("category,expected", [
    ("decisions", "decision"),
    ("Decisions", "decision"),
    ("AGENTS", "agent"),
    ("documentation", "documentation"),
    ("unknown-room", "unknown-room"),
    (None, "other"),
])
def test_kind_normalization(category, expected):
    item = _parse_item("title here  body here  (ref)", category)
    assert item is not None
    assert item["kind"] == expected
