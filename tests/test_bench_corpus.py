import json
import pytest
from copyclip.intelligence.cuaderno.bench.corpus import (
    load_corpus, CorpusError, corpus_sha,
)


def _write(tmp_path, rows):
    p = tmp_path / "c.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return str(p)


def test_loads_valid_corpus(tmp_path):
    rows = [{
        "id": "q1", "question": "¿cómo?", "category": "grounded_happy_path",
        "commit_sha": "e4400af", "question_lang": "es",
        "asserts": [{"type": "status_in", "value": ["answer"]}],
    }]
    items = load_corpus(_write(tmp_path, rows))
    assert len(items) == 1 and items[0]["id"] == "q1"


def test_rejects_unknown_assert_type(tmp_path):
    rows = [{"id": "q1", "question": "q", "category": "c", "commit_sha": "x",
             "question_lang": "es", "asserts": [{"type": "bogus"}]}]
    with pytest.raises(CorpusError, match="unknown assert type"):
        load_corpus(_write(tmp_path, rows))


def test_rejects_missing_required_field(tmp_path):
    rows = [{"id": "q1", "question": "q", "asserts": []}]  # no commit_sha/category/lang
    with pytest.raises(CorpusError):
        load_corpus(_write(tmp_path, rows))


def test_rejects_duplicate_ids(tmp_path):
    rows = [
        {"id": "dup", "question": "q", "category": "c", "commit_sha": "x",
         "question_lang": "es", "asserts": []},
        {"id": "dup", "question": "q2", "category": "c", "commit_sha": "x",
         "question_lang": "es", "asserts": []},
    ]
    with pytest.raises(CorpusError, match="duplicate"):
        load_corpus(_write(tmp_path, rows))


def test_corpus_sha_is_stable(tmp_path):
    p = _write(tmp_path, [{"id": "q1", "question": "q", "category": "c",
                           "commit_sha": "x", "question_lang": "es", "asserts": []}])
    assert corpus_sha(p) == corpus_sha(p)
    assert len(corpus_sha(p)) == 12
