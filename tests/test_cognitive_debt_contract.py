"""Contract invariants for the cognitive debt factor model.

Pins weights, severity thresholds, confidence thresholds, and the clamp
invariant so later weight tuning cannot silently break the public contract
described in ``docs/COGNITIVE_DEBT_CONTRACT.md``.
"""

import pytest

from copyclip.intelligence.cognitive_debt import (
    COGNITIVE_DEBT_FACTORS,
    CONTRACT_VERSION,
    SEVERITY_BUCKETS,
    _confidence_for,
    _severity_for,
    build_debt_breakdown,
)
from copyclip.intelligence.db import connect, init_schema

from tests.fixtures.cog_debt_fixtures import STABLE_NOW_TS, seed_mixed_debt_project


def test_factor_weights_sum_to_one():
    total = sum(f["weight"] for f in COGNITIVE_DEBT_FACTORS)
    assert abs(total - 1.0) < 1e-9


def test_factor_ids_are_unique():
    ids = [f["id"] for f in COGNITIVE_DEBT_FACTORS]
    assert len(ids) == len(set(ids))


def test_severity_buckets_cover_zero_to_hundred_without_gaps():
    # SEVERITY_BUCKETS is ordered with critical first (highest threshold) → low
    ordered = sorted(SEVERITY_BUCKETS, key=lambda entry: entry[1])
    thresholds = [entry[1] for entry in ordered]
    assert thresholds[0] == 0.0
    # strictly increasing thresholds (no duplicates)
    assert all(later > earlier for earlier, later in zip(thresholds, thresholds[1:]))


@pytest.mark.parametrize("value,expected", [
    (0.0, "low"),
    (24.0, "low"),
    (25.0, "medium"),
    (49.9, "medium"),
    (50.0, "high"),
    (74.0, "high"),
    (75.0, "critical"),
    (100.0, "critical"),
])
def test_severity_mapping_matches_contract(value, expected):
    assert _severity_for(value) == expected


@pytest.mark.parametrize("coverage,expected", [
    (0.0, "low"),
    (0.59, "low"),
    (0.6, "medium"),
    (0.84, "medium"),
    (0.85, "high"),
    (1.0, "high"),
])
def test_confidence_mapping_matches_contract(coverage, expected):
    assert _confidence_for(coverage) == expected


def test_contract_version_is_exposed_on_breakdown(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_mixed_debt_project(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=STABLE_NOW_TS)
    conn.close()
    assert breakdown["meta"]["contract_version"] == CONTRACT_VERSION


def test_score_stays_in_bounds_across_scopes(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_mixed_debt_project(conn, str(tmp_path))
    for scope_kind, scope_id in [
        ("file", "src/copyclip/mcp_server.py"),
        ("file", "src/copyclip/ask/answer.py"),
        ("file", "src/copyclip/new_module.py"),
        ("module", "copyclip.mcp"),
        ("project", "copyclip"),
    ]:
        breakdown = build_debt_breakdown(conn, pid, scope_kind, scope_id, now_ts=STABLE_NOW_TS)
        assert 0.0 <= breakdown["score"]["value"] <= 100.0
        assert breakdown["score"]["severity"] in {"low", "medium", "high", "critical"}
        assert breakdown["score"]["confidence"] in {"low", "medium", "high"}
    conn.close()


def test_weighted_contribution_matches_weight_times_normalized(tmp_path):
    conn = connect(str(tmp_path))
    init_schema(conn)
    pid = seed_mixed_debt_project(conn, str(tmp_path))
    breakdown = build_debt_breakdown(conn, pid, "file", "src/copyclip/mcp_server.py", now_ts=STABLE_NOW_TS)
    conn.close()
    for factor in breakdown["factor_breakdown"]:
        if not factor["signal_available"]:
            assert factor["weighted_contribution"] == 0.0
            continue
        expected = round(factor["weight"] * factor["normalized_contribution"], 4)
        assert abs(factor["weighted_contribution"] - expected) < 1e-9
