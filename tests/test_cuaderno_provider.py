import sqlite3

import pytest

from copyclip.intelligence.cuaderno.provider import (
    resolve_cuaderno_provider, build_cuaderno_client, provider_key_status,
    CuadernoProviderError, DEFAULT_MODELS, TOOL_INCAPABLE_MODELS,
)
from copyclip.intelligence.cuaderno.anthropic_client import AnthropicAdapter
from copyclip.intelligence.cuaderno.openai_client import OpenAICompatAdapter


def _conn_with_config(pairs):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT)")
    for k, v in pairs.items():
        conn.execute("INSERT INTO config(key,value) VALUES(?,?)", (k, v))
    conn.commit()
    return conn


def test_sqlite_overlay_selects_provider_and_model(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    conn = _conn_with_config({"cuaderno_provider": "deepseek", "cuaderno_model": "deepseek-chat"})
    r = resolve_cuaderno_provider(conn)
    assert r["provider"] == "deepseek"
    assert r["model"] == "deepseek-chat"
    assert r["api_key"] == "sk-ds"
    assert "deepseek.com" in r["base_url"]


def test_falls_back_to_default_model_when_unset(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-an")
    conn = _conn_with_config({"cuaderno_provider": "anthropic"})
    r = resolve_cuaderno_provider(conn)
    assert r["model"] == DEFAULT_MODELS["anthropic"]


def test_missing_key_raises_typed_error(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    conn = _conn_with_config({"cuaderno_provider": "deepseek"})
    with pytest.raises(CuadernoProviderError) as exc:
        resolve_cuaderno_provider(conn)
    assert exc.value.provider == "deepseek"


def test_tool_incapable_model_rejected(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    conn = _conn_with_config({"cuaderno_provider": "deepseek", "cuaderno_model": "deepseek-reasoner"})
    with pytest.raises(CuadernoProviderError) as exc:
        resolve_cuaderno_provider(conn)
    assert "tool" in str(exc.value).lower()
    assert "deepseek-reasoner" in TOOL_INCAPABLE_MODELS


def test_build_client_picks_adapter(monkeypatch):
    anth = build_cuaderno_client({"provider": "anthropic", "api_key": "k", "base_url": "u", "model": "m"})
    assert isinstance(anth, AnthropicAdapter)
    oai = build_cuaderno_client({"provider": "deepseek", "api_key": "k", "base_url": "u", "model": "m"})
    assert isinstance(oai, OpenAICompatAdapter)


def test_provider_key_status_is_non_raising(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    status = provider_key_status()
    assert status["deepseek"] is True
    assert status["anthropic"] is False
    assert status["openai"] is False


def test_resolve_judge_model_defaults():
    from copyclip.intelligence.cuaderno.provider import resolve_judge_model
    assert resolve_judge_model("anthropic", "claude-sonnet-4-5", overlay=None) == "claude-haiku-4-5"
    assert resolve_judge_model("deepseek", "deepseek-chat", overlay=None) == "deepseek-chat"
    assert resolve_judge_model("anthropic", "claude-sonnet-4-5", overlay="claude-opus-4-8") == "claude-opus-4-8"
