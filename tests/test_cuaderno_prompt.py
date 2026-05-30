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
    assert "stop reading" in low or "stop exploring" in low
