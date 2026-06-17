from copyclip.intelligence.cuaderno.prompts import (
    WIDGET_RECOVERY_DIRECTIVE_RUN, SYSTEM_PROMPT,
)


def test_run_directive_mentions_call_descriptor_fields():
    t = WIDGET_RECOVERY_DIRECTIVE_RUN
    assert "args" in t and "kwargs" in t and "ctor" in t
    assert "step through" in t.lower()


def test_system_prompt_playground_spec_documents_call_fields():
    s = SYSTEM_PROMPT
    assert '"args"' in s and '"kwargs"' in s and '"ctor"' in s
