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


from copyclip.intelligence.cuaderno import ask_stream
from tests.test_cuaderno_compositor import StubStream, _tool_stop, _content, _msg_stop


def test_meta_event_carries_question_language(tmp_path):
    # The meta event is yielded FIRST, before iter_compose_events runs or any
    # save_question touches the DB — so pull just that event and close the
    # generator (avoids save_question(conn=None) on the trailing frame event).
    client = StubStream([_msg_stop("end_turn", [])])
    gen = ask_stream.iter_ask_events(
        client=client, question="¿cómo funciona esto?", project_root=str(tmp_path),
        project_id=1, conn=None, session_id="s1", max_tool_rounds=1)
    meta = next(gen)
    gen.close()
    assert meta["type"] == "meta"
    assert meta["question_language"] == "es"


def test_persist_partial_sets_language_and_localizes(tmp_path, monkeypatch):
    saved = []
    monkeypatch.setattr(ask_stream, "save_question",
                        lambda conn, sid, q, frame: saved.append(frame))
    ask_stream._persist_partial(None, "s1", "¿cómo?", [], message="boom")
    assert saved[0].question_language == "es"
    es_text = saved[0].blocks[0].data["text"]
    saved.clear()
    ask_stream._persist_partial(None, "s1", "how does it work?", [], message="boom")
    assert saved[0].question_language == "en"
    assert saved[0].blocks[0].data["text"] != es_text  # localized
