# src/copyclip/llm/config.py
from __future__ import annotations
import os, pathlib, re
from typing import Any, Dict, Optional

try:
    import yaml  # PyYAML
except Exception:
    yaml = None  # validaremos más abajo

SEARCH_LOCATIONS = [
    lambda: os.getenv("COPYCLIP_LLM_CONFIG"),
    lambda: os.path.join(os.getcwd(), "llm.yaml"),
    lambda: os.path.join(pathlib.Path.home(), ".config", "copyclip", "llm.yaml"),
    lambda: os.path.join(pathlib.Path.home(), ".config", "llm.yaml"),
    lambda: os.path.join(pathlib.Path.home(), ".copyclip_llm.yaml"),
]

ENV_PREFIX = "COPYCLIP_"

# Brief: _read_yaml
def _read_yaml(path: str) -> Dict[str, Any]:
    if not yaml:
        raise RuntimeError("PyYAML is required. Install with: pip install pyyaml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError("llm.yaml must be a mapping at top-level")
        return data

# Brief: _resolve_secret
def _resolve_secret(v: Any) -> Any:
    if isinstance(v, str):
        m = re.match(r"\$\{ENV:([A-Z0-9_]+)\}", v)
        if m:
            return os.getenv(m.group(1))
        m = re.match(r"\$\{FILE:(.+)\}", v)
        if m:
            p = os.path.expanduser(m.group(1).strip())
            try:
                return pathlib.Path(p).read_text(encoding="utf-8").strip()
            except Exception:
                return None
    return v
# Brief: _merge_dict

# Brief: _merge_dict
def _merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_dict(out[k], v)
        else:
            out[k] = v
    return out

# Brief: load_config
def load_config(cli_path: Optional[str]) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    # 1) YAML (CLI/ENV/proyecto/usuario)
    path = cli_path
    if not path:
        for finder in SEARCH_LOCATIONS:
            p = finder()
            if p and os.path.exists(p):
                path = p; break
    if path and os.path.exists(path):
        cfg = _read_yaml(path)

    # 2) ENV overrides estilo COPYCLIP_LLM_*
    #   COPYCLIP_LLM_PROVIDER, COPYCLIP_LLM_MODEL, COPYCLIP_LLM_ENDPOINT, COPYCLIP_LLM_TIMEOUT, COPYCLIP_LLM_API_KEY
    env_over = {}
    prov = os.getenv(f"{ENV_PREFIX}LLM_PROVIDER")
    if prov: env_over["default_provider"] = prov
    model = os.getenv(f"{ENV_PREFIX}LLM_MODEL")
    endpoint = os.getenv(f"{ENV_PREFIX}LLM_ENDPOINT")
    timeout = os.getenv(f"{ENV_PREFIX}LLM_TIMEOUT")
    api_key = os.getenv(f"{ENV_PREFIX}LLM_API_KEY")
    if any([model, endpoint, timeout]):
        dp = env_over.setdefault("defaults", {})
        if timeout: dp["timeout"] = int(timeout)
        # si hay default_provider y sección de providers, ponemos overrides ahí
        if prov:
            prov_map = env_over.setdefault("providers", {}).setdefault(prov, {})
            if model: prov_map["model"] = model
            if endpoint: prov_map["endpoint"] = endpoint
    if api_key:
        target_prov = prov or env_over.get("default_provider") or "deepseek"
        env_over.setdefault("providers", {}).setdefault(target_prov, {})["api_key"] = api_key

    cfg = _merge_dict(cfg, env_over)
    # 3) Normaliza y resuelve secrets
    providers = cfg.get("providers", {}) or {}
    for name, c in providers.items():
        if isinstance(c, dict):
            if not c.get("api_key"):
                if name.lower() == "openai":
                    c["api_key"] = os.getenv("OPENAI_API_KEY")
                elif name.lower() == "anthropic":
                    c["api_key"] = os.getenv("ANTHROPIC_API_KEY")
                elif name.lower() == "deepseek":
                    c["api_key"] = os.getenv("DEEPSEEK_API_KEY")
    return cfg

# Brief: resolve_settings
def resolve_settings(
    cfg: Dict[str, Any],
    cli_provider: Optional[str] = None,
    cli_model: Optional[str] = None,
    cli_endpoint: Optional[str] = None,
    cli_timeout: Optional[int] = None,
) -> Dict[str, Any]:
    provider = (cli_provider or cfg.get("default_provider") or "deepseek").lower()
    defaults = cfg.get("defaults", {}) or {}
    pcfg = (cfg.get("providers", {}) or {}).get(provider, {}) or {}
    settings = {
        "provider": provider,
        "model": cli_model or pcfg.get("model"),
        "api_key": pcfg.get("api_key"),
        "endpoint": cli_endpoint or pcfg.get("endpoint"),
        "timeout": int(cli_timeout if cli_timeout is not None else (defaults.get("timeout") or 20)),
        "batch_size": int(defaults.get("batch_size") or 8),
        "extra_headers": pcfg.get("extra_headers", {}) or {},
    }
    return settings

# Brief: pretty_settings
def pretty_settings(s: Dict[str, Any]) -> str:
    ak = "set" if s.get("api_key") else "missing"
    return (
        f"provider={s['provider']} "
        f"model={s.get('model') or '-'} "
        f"endpoint={s.get('endpoint') or '-'} "
        f"timeout={s['timeout']}s "
        f"api_key={ak}"
    )
