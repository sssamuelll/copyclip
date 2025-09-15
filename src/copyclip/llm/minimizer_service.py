# src/copyclip/llm/minimizer_service.py
from __future__ import annotations
import os, re
import sys
from typing import Optional, Dict, Any, Tuple, List
from ..llm_client import LLMClientFactory
from .config import load_config
from .provider_config import resolve_provider, ProviderConfigError

def _collapse_blank_lines(text: str) -> str:
    import re
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    return re.sub(r"\n{3,}", "\n\n", text)

async def contextual_minimize(
    code: str, file_ext: str, doc_lang: str,
    model_hint: Optional[str] = None,
    provider_hint: Optional[str] = None,
    file_path: Optional[str] = None
) -> Tuple[Optional[str], Optional[Exception], Dict[str, Any]]:
    """
    Resolve provider via provider_config with precedence CLI > preset/config > default.
    If provider comes from CLI and is misconfigured, fail fast (no silent fallback).
    """
    cfg = load_config(os.getenv("COPYCLIP_LLM_CONFIG"))
    cli_provider = provider_hint or os.getenv("COPYCLIP_LLM_PROVIDER")

    # Primary provider (raises if misconfigured)
    try:
        primary = resolve_provider(cli_provider, cfg)
    except ProviderConfigError as e:
        return None, e, {"provider": cli_provider or "default"}

    # Only try fallbacks if NO CLI provider was set (optional)
    providers: List[Dict[str, Any]] = [primary]
    if not cli_provider:
        env_fallbacks = [p.strip() for p in (os.getenv("COPYCLIP_LLM_FALLBACKS", "") or "").split(",") if p.strip()]
        seen = {primary["name"]}
        for fb in env_fallbacks:
            try:
                rp = resolve_provider(fb, cfg)
                if rp["name"] not in seen:
                    providers.append(rp); seen.add(rp["name"])
            except ProviderConfigError:
                continue

    # Resolve prompt (optional)
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "contextual_minimizer.md")
    system_prompt = None
    if os.path.exists(prompt_path) and os.path.isfile(prompt_path):
        system_prompt = open(prompt_path, "r", encoding="utf-8").read()

    last_err: Optional[BaseException] = None
    last_settings: Dict[str, Any] = {
        "provider": primary["name"],
        "model": primary.get("model"),
        "endpoint": primary.get("base_url"),
        "timeout": primary.get("timeout", 60),
        "extra_headers": primary.get("extra_headers", {}),
    }

    # Try providers in order until one succeeds
    for prov in providers:
        try:
            s_try = {
                "provider": prov["name"],
                "model": prov.get("model"),
                "endpoint": prov.get("base_url"),
                "timeout": int(prov.get("timeout") or 60),
                "extra_headers": prov.get("extra_headers") or {},
                "api_key": prov.get("api_key"),
            }
            last_settings = s_try
            client = LLMClientFactory.create(
                s_try["provider"],
                api_key=s_try.get("api_key"),
                model=s_try.get("model"),
                endpoint=s_try.get("endpoint"),
                timeout=s_try["timeout"],
                extra_headers=s_try.get("extra_headers"),
            )
            result = await client.minimize_code_contextually(code, file_ext, doc_lang, system_prompt)
            result = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", (result or "").strip(), flags=re.M)
            result = _collapse_blank_lines(result)
            if not result.endswith("\n"):
                result += "\n"
            return result, None, s_try
        except Exception as e:
            last_err = e
            continue
    # If all providers failed, return the last error
    return None, last_err, last_settings
