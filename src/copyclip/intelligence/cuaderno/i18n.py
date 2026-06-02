"""Localized strings the CODE injects into a user-facing frame (NOT the model).
Mirrors the question's detected language; unknown/absent -> English. Two locales
only (the detector serves es/en); no i18n library."""
from __future__ import annotations

from typing import Optional

_STRINGS = {
    "en": {
        "fallback": ("I couldn't finish this turn — {reason}. Try rephrasing, or "
                     "ask a narrower question (a specific file, function, or commit)."),
        "partial": "This turn was interrupted ({reason}). Re-ask to retry.",
        "partial_default_reason": "the stream ended early",
    },
    "es": {
        "fallback": ("No pude terminar este turno — {reason}. Reformula, o haz una "
                     "pregunta más acotada (un archivo, función o commit específico)."),
        "partial": "Este turno se interrumpió ({reason}). Vuelve a preguntar para reintentar.",
        "partial_default_reason": "el stream se cortó temprano",
    },
}


def tr(key: str, lang: Optional[str], **kwargs) -> str:
    table = _STRINGS["es"] if lang == "es" else _STRINGS["en"]
    template = table.get(key) or _STRINGS["en"][key]
    return template.format(**kwargs) if kwargs else template
