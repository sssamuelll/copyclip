from copyclip.intelligence.cuaderno.schema import (
    Frame, Block, frame_to_dict, frame_from_dict,
)


def test_frame_carries_question_language_round_trip():
    f = Frame(question="¿cómo?", blocks=[Block.paragraph("x")],
              status="answer", verdict=None, question_language="es")
    d = frame_to_dict(f)
    assert d["question_language"] == "es"
    back = frame_from_dict(d)
    assert back.question_language == "es"


def test_legacy_frame_defaults_question_language_none():
    # A stored frame from before this field existed.
    d = {"question": "q", "blocks": [], "status": "legacy"}
    assert frame_from_dict(d).question_language is None
