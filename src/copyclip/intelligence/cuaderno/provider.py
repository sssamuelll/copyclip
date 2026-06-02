from __future__ import annotations

import os
import sqlite3
from typing import Optional, TypedDict

from ...llm.config import load_config
from ...llm.provider_config import PROVIDERS, resolve_provider, ProviderConfigError
from .anthropic_client import AnthropicAdapter
from .openai_client import OpenAICompatAdapter

# Default cuaderno model per provider when the user has not chosen one.
DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-5",
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o",
}

# Models that cannot drive tool-calling and therefore cannot run the cuaderno's
# agentic emit_block protocol.
TOOL_INCAPABLE_MODELS: frozenset[str] = frozenset({"deepseek-reasoner"})

# Cheap default judge model per provider (the judge is classification, not authoring).
JUDGE_DEFAULT_MODELS: dict[str, str] = {"anthropic": "claude-haiku-4-5"}


def resolve_judge_model(provider: str, answer_model: str, overlay: Optional[str]) -> str:
    """The judge model: an explicit overlay wins; else a cheap per-provider
    default; else the answer model (always serveable by the current provider)."""
    if overlay:
        return overlay
    return JUDGE_DEFAULT_MODELS.get(provider, answer_model)

# Providers whose wire format is the Anthropic Messages API.
_ANTHROPIC_PROVIDERS: frozenset[str] = frozenset({"anthropic"})


class ResolvedCuaderno(TypedDict):
    provider: str
    api_key: str
    base_url: str
    model: str


class CuadernoProviderError(RuntimeError):
    def __init__(self, message: str, provider: str):
        super().__init__(message)
        self.provider = provider


def _read_config_key(conn: Optional[sqlite3.Connection], key: str) -> Optional[str]:
    if conn is None:
        return None
    try:
        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row and row[0] else None


def resolve_cuaderno_provider(conn: Optional[sqlite3.Connection]) -> ResolvedCuaderno:
    """Resolve the cuaderno's provider/model/key/base_url.

    Layering: the SQLite `config` overlay (cuaderno_provider/cuaderno_model,
    written by the UI selector) selects which provider + model; the API key and
    base URL come from resolve_provider (llm.yaml/ENV). Raises
    CuadernoProviderError (naming the provider) when the key is missing or the
    chosen model cannot do tool-calling.
    """
    overlay_provider = _read_config_key(conn, "cuaderno_provider")
    overlay_model = _read_config_key(conn, "cuaderno_model")

    cfg = load_config(None)
    try:
        resolved = resolve_provider(overlay_provider, cfg)
    except ProviderConfigError as exc:
        provider = (overlay_provider or cfg.get("default_provider") or "deepseek").lower()
        raise CuadernoProviderError(
            f"LLM not configured for provider '{provider}': {exc}. "
            f"Run `copyclip start` or open Settings to add the key.",
            provider,
        ) from exc

    provider = resolved["name"]
    model = overlay_model or resolved.get("model") or DEFAULT_MODELS.get(provider, "")

    if model in TOOL_INCAPABLE_MODELS:
        raise CuadernoProviderError(
            f"Model '{model}' does not support tool-calling, which the cuaderno "
            f"requires. Pick a tool-capable model (e.g. deepseek-chat).",
            provider,
        )

    return ResolvedCuaderno(
        provider=provider,
        api_key=resolved["api_key"],
        base_url=resolved["base_url"],
        model=model,
    )


def build_cuaderno_client(resolved: ResolvedCuaderno):
    """Build the adapter matching the resolved provider's wire format."""
    if resolved["provider"] in _ANTHROPIC_PROVIDERS:
        return AnthropicAdapter(api_key=resolved["api_key"])
    return OpenAICompatAdapter(api_key=resolved["api_key"], base_url=resolved["base_url"])


def provider_key_status() -> dict[str, bool]:
    """Non-raising per-provider key check for the selector (does NOT call the
    fail-fast resolve_provider)."""
    return {
        name: bool((os.environ.get(meta.api_key_env) or "").strip())
        for name, meta in PROVIDERS.items()
    }
