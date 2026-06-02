from collections import Counter
from copyclip.intelligence.cuaderno.bench.corpus import load_corpus

CORPUS = "corpus/cuaderno-bench.jsonl"
REQUIRED_CATEGORIES = {
    "what_vs_how", "grounded_happy_path", "must_abstain", "must_not_fabricate",
    "fabricated_grounding_bait", "meta_about_tutor", "language_fidelity",
    "temporal_causal", "multi_hop_cross_file",
}


def test_corpus_loads_and_validates():
    items = load_corpus(CORPUS)
    assert len(items) >= 18  # ~20-30 target; floor guards against truncation


def test_corpus_covers_all_nine_categories():
    items = load_corpus(CORPUS)
    cats = set(it["category"] for it in items)
    missing = REQUIRED_CATEGORIES - cats
    assert not missing, f"corpus missing categories: {missing}"


def test_abstain_categories_assert_abstain_status():
    items = load_corpus(CORPUS)
    for it in items:
        if it["category"] in ("must_abstain", "must_not_fabricate"):
            types = {a["type"] for a in it["asserts"]}
            assert "status_in" in types or "status_is" in types, \
                f"{it['id']} must assert its abstention status"
