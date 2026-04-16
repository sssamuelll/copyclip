import re

from copyclip.intelligence.ask_project import build_ask_response
from copyclip.intelligence.db import connect, init_schema
from tests.ask_project_eval_fixture import REPRESENTATIVE_ASK_EVAL_CASES, seed_representative_ask_project


def _case_slug(case: dict) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", f"{case['scenario']}_{case['question'].lower()}").strip("_")


def test_build_ask_response_matches_representative_eval_cases(tmp_path):
    for case in REPRESENTATIVE_ASK_EVAL_CASES:
        root = str(tmp_path / _case_slug(case))
        conn = connect(root)
        init_schema(conn)
        project_id = seed_representative_ask_project(
            conn,
            root,
            include_contradiction=case["scenario"] == "contradiction",
        )

        response = build_ask_response(conn, project_id, case["question"])
        assert response["answer_kind"] == case["answer_kind"]
        assert response["grounded"] is case["grounded"]
        assert response["confidence"] == case["confidence"]
        assert set(case["required_citation_types"]).issubset({citation["type"] for citation in response["citations"]})
        assert set(case["required_evidence_groups"]).issubset(
            {name for name, items in response["evidence"].items() if items}
        )
        assert response["next_drill_down"]["type"] == case["drill_down_type"]
        if case["answer_kind"] == "contradiction_detected":
            assert any("intent_drift" in item["label"] for item in response["evidence"]["risks"])

        conn.close()


def test_build_ask_response_backfills_supporting_file_evidence_when_top_results_are_non_file(tmp_path):
    root = str(tmp_path / "backfill")
    conn = connect(root)
    init_schema(conn)
    project_id = seed_representative_ask_project(conn, root)

    response = build_ask_response(conn, project_id, "what did we decide about auth session rollout?")
    assert response["answer_kind"] == "grounded_answer"
    assert response["evidence"]["files"]
    assert any(
        "backfilled" in " ".join(file_item["why_selected"]).lower()
        for file_item in response["evidence"]["files"]
    )

    conn.close()
