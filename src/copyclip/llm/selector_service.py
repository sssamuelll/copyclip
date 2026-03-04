# src/copyclip/llm/selector_service.py
from __future__ import annotations
import os
from typing import Optional, Dict, Any, List
from ..llm_client import LLMClientFactory
from .config import load_config
from .provider_config import resolve_provider, ProviderConfigError

async def select_relevant_files(
    files: List[str], intent: str,
    provider_hint: Optional[str] = None
) -> List[str]:
    cfg = load_config(os.getenv("COPYCLIP_LLM_CONFIG"))
    cli_provider = provider_hint or os.getenv("COPYCLIP_LLM_PROVIDER")

    try:
        prov = resolve_provider(cli_provider, cfg)
    except ProviderConfigError:
        # If no LLM configured, just return top 5 files as fallback
        return files[:5]

    try:
        client = LLMClientFactory.create(
            prov["name"],
            api_key=prov.get("api_key"),
            model=prov.get("model"),
            endpoint=prov.get("base_url"),
            timeout=int(prov.get("timeout") or 60),
            extra_headers=prov.get("extra_headers"),
        )
        return await client.select_relevant_files(files, intent)
    except Exception:
        return files[:5]
