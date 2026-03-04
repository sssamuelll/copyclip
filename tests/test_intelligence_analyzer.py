from copyclip.intelligence.analyzer import _complexity_score, _is_test_path


def test_is_test_path_variants():
    assert _is_test_path("tests/test_api.py")
    assert _is_test_path("src/foo/bar.spec.ts")
    assert _is_test_path("src/foo/bar.test.js")
    assert not _is_test_path("src/foo/bar.ts")


def test_complexity_score_detects_control_flow():
    low = "def x():\n    return 1\n"
    high = """
def y(a):
    if a:
        for i in range(3):
            if i % 2:
                try:
                    pass
                except Exception:
                    pass
    else:
        while a:
            break
"""
    assert _complexity_score(high, "python") > _complexity_score(low, "python")
    assert _complexity_score(low, "python") >= 1
