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


from copyclip.intelligence.cuaderno.i18n import tr
from copyclip.intelligence.cuaderno import compositor


def test_tr_picks_locale_and_falls_back_to_en():
    assert tr("fallback", "es", reason="x") != tr("fallback", "en", reason="x")
    # unknown / None -> English
    assert tr("fallback", "unknown", reason="x") == tr("fallback", "en", reason="x")
    assert tr("fallback", None, reason="x") == tr("fallback", "en", reason="x")


def test_fallback_frame_sets_language_and_localizes_text():
    es = compositor._fallback_frame("¿cómo funciona el compositor?", "budget")
    en = compositor._fallback_frame("how does the compositor work?", "budget")
    assert es.question_language == "es"
    assert en.question_language == "en"
    es_text = es.blocks[0].data["text"]
    en_text = en.blocks[0].data["text"]
    assert es_text != en_text  # localized
    assert es.status == "fallback" and en.status == "fallback"


def test_seal_sets_question_language():
    fd = compositor._seal("¿qué es esto?", [Block.paragraph("respuesta")],
                          "answer", {"source": "cheap"})
    assert fd["question_language"] == "es"
