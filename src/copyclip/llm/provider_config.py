# src/copyclip/llm/provider_config.py

from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass
from typing import Dict, Any, Mapping, Optional, TypedDict
from urllib.parse import urlparse

# Keep a stable logger name so ops can filter consistently
logger = logging.getLogger("copyclip.provider")


class ProviderConfigError(RuntimeError):
    """Raised when provider resolution/validation fails."""


# --- Single source of truth: provider metadata & aliases ---------------------

@dataclass(frozen=True)
class ProviderMeta:
    api_key_env: str
    base_url_env: str
    default_base_url: str
    default_model_env: Optional[str] = None  # e.g. OPENAI_MODEL
    extra_headers_env: Optional[str] = None  # e.g. OPENAI_EXTRA_HEADERS (JSON)


PROVIDERS: Mapping[str, ProviderMeta] = {
    "openai": ProviderMeta(
        api_key_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        default_base_url="https://api.openai.com/v1",
        default_model_env="OPENAI_MODEL",
        extra_headers_env="OPENAI_EXTRA_HEADERS",
    ),
    "deepseek": ProviderMeta(
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_BASE_URL",
        default_base_url="https://api.deepseek.com/v1",
        default_model_env="DEEPSEEK_MODEL",
        extra_headers_env="DEEPSEEK_EXTRA_HEADERS",
    ),
    "anthropic": ProviderMeta(
        api_key_env="ANTHROPIC_API_KEY",
        base_url_env="ANTHROPIC_BASE_URL",
        default_base_url="https://api.anthropic.com/v1",
        default_model_env="ANTHROPIC_MODEL",
        extra_headers_env="ANTHROPIC_EXTRA_HEADERS",
    ),
}

# Friendly aliases commonly used by humans
ALIASES: Mapping[str, str] = {
    "oai": "openai",
    "gpt": "openai",
    "claude": "anthropic",
    "ds": "deepseek",
}

DEFAULT_PROVIDER = "deepseek"


class ResolvedProvider(TypedDict):
    name: str
    api_key: str
    base_url: str
    model: Optional[str]
    timeout: int
    extra_headers: Dict[str, str]


# --- Small, testable helpers -------------------------------------------------

def _normalize_provider(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    key = name.strip().lower()
    return ALIASES.get(key, key)


def _read_env(name: Optional[str]) -> Optional[str]:
    """Return env var trimmed or None if unset/empty."""
    if not name:
        return None
    val = os.environ.get(name)
    if val is None:
        return None
    val = val.strip()
    return val or None


def _valid_url(url: str) -> bool:
    p = urlparse(url)
    return bool(p.scheme and p.netloc)


def _safe_url_for_log(url: str) -> str:
    """Return scheme://host for logs (no paths/queries)."""
    p = urlparse(url)
    if p.scheme and p.netloc:
        return f"{p.scheme}://{p.netloc}"
    return url


def _resolve_base_url(meta: ProviderMeta) -> str:
    # priority: explicit env > default from meta; validate format
    env_url = _read_env(meta.base_url_env)
    url = env_url or meta.default_base_url
    if not _valid_url(url):
        # warn and fall back to default if env is malformed
        if env_url:
            logger.warning(
                json.dumps(
                    {
                        "event": "provider_base_url_invalid",
                        "env": meta.base_url_env,
                        "value_preview": _safe_url_for_log(env_url),
                        "action": "fallback_to_default",
                    }
                )
            )
        url = meta.default_base_url
    return url


def _clamp_timeout(raw: Any, default: int = 60, min_s: int = 1, max_s: int = 600) -> int:
    try:
        v = int(raw)
    except Exception:
        return default
    return max(min_s, min(max_s, v))


def _merge_headers(cfg_headers: Any, env_json: Optional[str]) -> Dict[str, str]:
    """Merge config headers (dict) with env JSON headers; env wins on conflicts."""
    result: Dict[str, str] = {}
    if isinstance(cfg_headers, dict):
        for k, v in cfg_headers.items():
            if isinstance(k, str) and isinstance(v, str):
                result[k] = v

    if env_json:
        try:
            parsed = json.loads(env_json)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if isinstance(k, str) and isinstance(v, str):
                        result[k] = v  # env wins
            else:
                logger.warning(
                    json.dumps(
                        {
                            "event": "provider_extra_headers_invalid",
                            "reason": "env_not_a_dict",
                        }
                    )
                )
        except Exception as e:
            logger.warning(
                json.dumps(
                    {
                        "event": "provider_extra_headers_invalid",
                        "reason": "json_parse_error",
                        "error": str(e),
                    }
                )
            )
    return result


# --- Public API --------------------------------------------------------------

def resolve_provider(cli_provider: Optional[str], config: Dict[str, Any]) -> ResolvedProvider:
    """
    Resolve the LLM provider with precedence: CLI > preset/config > default.
    Validates API key and base URL. Raises ProviderConfigError on failure.

    Returns:
        ResolvedProvider dict with:
            - name: canonical provider name (e.g., "openai")
            - api_key: non-empty API key
            - base_url: validated base URL
            - model: resolved default model (env > config > None)
            - timeout: clamped integer seconds [1..600]
            - extra_headers: merged headers (config + optional ENV JSON), strings only

    Notes:
        * No sys.exit here: callers (CLI) decide how to handle errors.
        * We log a single 'provider_resolution' INFO event (safe fields only).
    """
    # Determine requested providers
    preset_provider = config.get("default_provider")
    selected_source = "default"

    selected = DEFAULT_PROVIDER
    if cli_provider:
        selected_source = "cli"
        selected = cli_provider
    elif preset_provider:
        selected_source = "preset"
        selected = preset_provider

    selected = _normalize_provider(selected)  # aliases + lowercase

    if not selected or selected not in PROVIDERS:
        supported = ", ".join(sorted(PROVIDERS.keys()))
        raise ProviderConfigError(f"Unknown provider '{selected}'. Supported providers: {supported}")

    meta = PROVIDERS[selected]

    # API key (required). If missing and source == cli, fail fast (no fallback).
    api_key = _read_env(meta.api_key_env)
    if not api_key:
        src_text = "via CLI flag" if selected_source == "cli" else f"from {selected_source}"
        raise ProviderConfigError(
            f"Provider '{selected}' selected {src_text} but '{meta.api_key_env}' is not set."
        )

    base_url = _resolve_base_url(meta)

    # Per-provider config overlays
    providers_cfg = config.get("providers", {})
    sel_cfg = providers_cfg.get(selected, {}) if isinstance(providers_cfg, dict) else {}
    defaults_cfg = config.get("defaults", {}) if isinstance(config.get("defaults"), dict) else {}

    # Model resolution: env override > config > None
    model_from_env = _read_env(meta.default_model_env) if meta.default_model_env else None
    model = model_from_env or sel_cfg.get("model")

    # Timeout (int) and extra headers (dict)
    timeout = _clamp_timeout(sel_cfg.get("timeout", defaults_cfg.get("timeout", 60)))
    cfg_headers = sel_cfg.get("extra_headers", {})
    env_headers_json = _read_env(meta.extra_headers_env)
    extra_headers = _merge_headers(cfg_headers, env_headers_json)

    # Observability: single startup info log (safe fields only)
    logger.info(
        json.dumps(
            {
                "event": "provider_resolution",
                "cli": _normalize_provider(cli_provider) or "none",
                "preset": _normalize_provider(preset_provider) or "none",
                "selected": selected,
                "source": selected_source,
                "base_url_host": _safe_url_for_log(base_url),
                "fallback": False,
            }
        )
    )

    return ResolvedProvider(
        name=selected,
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
        extra_headers=extra_headers,
    )
