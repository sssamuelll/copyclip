import shutil
import subprocess
import pytest

from copyclip.intelligence.cuaderno.bench.runner import run_one, git_file_length_fn
from copyclip.intelligence.cuaderno.bench.asserts import AssertContext
from copyclip.intelligence.cuaderno.bench.score import scorecard
from tests.test_cuaderno_compositor import StubStream, _tool_stop, _content, _msg_stop

FIXTURE = "tests/fixtures/bench_fixture_repo"


@pytest.fixture
def repo(tmp_path):
    dst = tmp_path / "repo"
    shutil.copytree(FIXTURE, dst)
    subprocess.run(["git", "-C", str(dst), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(dst), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(dst), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "init"], check=True)
    sha = subprocess.run(["git", "-C", str(dst), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    return str(dst), sha


def test_git_file_length_fn_reads_pinned_sha(repo):
    root, sha = repo
    fn = git_file_length_fn(root, sha)
    assert fn("sample.py") == 6
    assert fn("does_not_exist.py") is None


def test_run_one_against_fixture_scores_deterministically(repo):
    root, sha = repo
    # Script an answer that cites sample.py lines 1-2 (within the 6-line file).
    cit = {"kind": "path", "path": "sample.py", "line_start": 1, "line_end": 2}
    turn = [
        _tool_stop("b1", "emit_block",
                   {"kind": "code_block", "code": "def greet", "language": "python",
                    "citation": cit}),
        _tool_stop("f1", "finish", {}),
        _msg_stop("tool_use", [
            _content("b1", "emit_block",
                     {"kind": "code_block", "code": "def greet", "language": "python",
                      "citation": cit}),
            _content("f1", "finish", {}),
        ]),
    ]
    # Citation asserts only (no language_is: a code_block carries no `text`, so
    # detect_language over the answer would be "unknown" — out of scope for this
    # citation-focused integration test). max_tool_rounds=1 seals without retry.
    item = {"id": "fx1", "question": "what does greet do?", "category": "grounded_happy_path",
            "commit_sha": sha, "question_lang": "en",
            "asserts": [{"type": "cites_path_matching", "value": "sample\\.py$"},
                        {"type": "cited_lines_within_eof"}]}
    ctx = AssertContext(file_length_fn=git_file_length_fn(root, sha))
    rec = run_one(item=item, client=StubStream([turn]), judge=None,
                  answer_model="claude-sonnet-4-5", project_root=root,
                  project_id=1, conn=None, assert_ctx=ctx, max_tool_rounds=1)
    outcomes = {a["type"]: a["outcome"] for a in rec.asserts}
    assert outcomes["cites_path_matching"] == "pass"
    assert outcomes["cited_lines_within_eof"] == "pass"
    sc = scorecard([rec])
    assert sc["n_questions"] == 1
