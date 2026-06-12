"""Keep the system prompt in sync with the tools and behavior it relies on."""
from copyclip.intelligence.cuaderno.prompts import SYSTEM_PROMPT
from copyclip.intelligence.cuaderno.tool_catalog import build_tool_definitions


def test_prompt_teaches_list_dir_orientation():
    # The orientation tool must be named in the prompt, and must actually exist.
    assert "list_dir" in SYSTEM_PROMPT
    assert "list_dir" in {t["name"] for t in build_tool_definitions()}


def test_prompt_guides_reading_files_not_directories():
    assert "directory" in SYSTEM_PROMPT or "folder" in SYSTEM_PROMPT.lower()


def test_prompt_does_not_assume_project_is_analyzed():
    # The old prompt asserted the project HAS been analyzed; that lie made the
    # model burn rounds on an empty symbols index. It must now be conditional.
    assert "has been analyzed" not in SYSTEM_PROMPT


def test_prompt_pushes_to_answer_rather_than_over_explore():
    low = SYSTEM_PROMPT.lower()
    # The prompt must discourage endless exploration once enough is read.
    assert "stop reading" in low or "stop exploring" in low or "do not keep exploring" in low


def test_prompt_requires_language_mirroring():
    low = SYSTEM_PROMPT.lower()
    assert "language" in low and ("same language" in low or "user's language" in low)


def test_prompt_requires_grounding_before_answering():
    low = SYSTEM_PROMPT.lower()
    assert "before" in low and ("read" in low or "evidence" in low)


def test_prompt_requires_answering_the_question_asked():
    low = SYSTEM_PROMPT.lower()
    assert "asked" in low or ("how" in low and "what" in low)


def test_prompt_teachback_is_optional_predict_from_site():
    # ⑥ corrected (cognitive-load doctrine): teach-back is an OPTIONAL self-test,
    # predict-from-SITE not recall (a reader who never wrote the code has nothing
    # to recall). The DEFAULT is to explain by altitude, never to quiz. The reveal
    # lands BESIDE their guess.
    low = SYSTEM_PROMPT.lower()
    assert "self-test" in low or "optional" in low
    assert "from its name" in low
    assert "beside" in low


def test_prompt_teaches_altitude_and_descent():
    # The organizing invariant: lower the COST OF REACHING the structure, never the
    # structure; one anchored lead → descend; every claim has a reachable descent.
    low = SYSTEM_PROMPT.lower()
    assert "cost of reaching" in low
    assert "descend" in low or "descent" in low
    assert "legible" in low
    assert "reachable" in low


def test_prompt_forbids_optimizing_felt_load():
    # Load is a state in a skull, not a property of an utterance; the substrate
    # cannot see it, so the tool must never optimize for that feeling (= W4-3 score
    # reborn). It optimizes the path to the code, not the felt drop.
    low = SYSTEM_PROMPT.lower()
    assert "load" in low
    assert "cannot see" in low or "never optimize" in low or "feel simple" in low


def test_prompt_forbids_grading_the_teachback_explanation():
    # The teach-back diff ("you missed X") is INFER reading a mind — forbidden.
    # The explanation is never scored, graded, or diffed against the code.
    low = SYSTEM_PROMPT.lower()
    assert "missed" in low or "got wrong" in low
    assert "never score" in low or "never grade" in low or "do not score" in low


def test_judge_prompt_demands_structured_verdict_and_responsiveness():
    from copyclip.intelligence.cuaderno.prompts import JUDGE_PROMPT
    low = JUDGE_PROMPT.lower()
    assert "json" in low
    assert "decision" in low and "responsive" in low and "world" in low
    assert ("mechanism" in low or "how it works" in low)
    assert "consulted_empty" in low and "not_consulted" in low
