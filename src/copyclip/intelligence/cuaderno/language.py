from __future__ import annotations

import re

# Spanish-only orthographic signals — any one is decisive.
_ES_CHARS = set("áéíóúñ¿¡")
_ES_WORDS = {
    "el", "la", "los", "las", "un", "una", "qué", "que", "cómo", "como",
    "por", "para", "dónde", "donde", "cuál", "cual", "funciona", "hace",
    "y", "de", "es", "con", "sin", "porque", "cuando", "este", "esta",
}
_EN_WORDS = {
    "the", "how", "what", "why", "does", "do", "is", "are", "a", "an",
    "of", "and", "to", "in", "this", "that", "where", "which", "with", "for",
}


def detect_language(text: str) -> str:
    """Return 'es', 'en', or 'unknown'. Cheap, dependency-free, biased toward
    the es/en pair the cuaderno actually serves. Spanish orthography (accents,
    inverted punctuation) is decisive; otherwise a stopword vote decides."""
    if not text:
        return "unknown"
    low = text.lower()
    if any(ch in _ES_CHARS for ch in low):
        return "es"
    words = re.findall(r"[a-záéíóúñ]+", low)
    if len(words) < 2:
        return "unknown"
    es = sum(1 for w in words if w in _ES_WORDS)
    en = sum(1 for w in words if w in _EN_WORDS)
    if es == en:
        return "unknown"
    return "es" if es > en else "en"


def languages_match(a: str, b: str) -> bool:
    """Unknown is compatible with anything (we never penalize on uncertainty)."""
    if a == "unknown" or b == "unknown":
        return True
    return a == b
