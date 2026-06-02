from copyclip.intelligence.cuaderno.language import detect_language, languages_match


def test_detects_spanish_question():
    assert detect_language("¿cómo funciona el analizador?") == "es"


def test_detects_english_question():
    assert detect_language("how does the analyzer work?") == "en"


def test_short_ambiguous_is_unknown():
    assert detect_language("ok") == "unknown"


def test_accent_or_inverted_punctuation_forces_spanish():
    assert detect_language("como funciona?") == "es" or detect_language("¿y?") == "es"


def test_languages_match_treats_unknown_as_compatible():
    assert languages_match("unknown", "en")
    assert languages_match("es", "unknown")
    assert languages_match("es", "es")
    assert not languages_match("es", "en")
