# src/copyclip/llm_client.py
from __future__ import annotations
import os
import importlib
import logging
import asyncio
import time
import aiohttp
import json as _json
import re
from typing import List, Optional, Protocol, Dict, Any, Iterator
from .llm.provider_config import ProviderConfigError

from copyclip.llm.metrics import metrics_collector

# Brief: _get_config_value
def _get_config_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """Fetch configuration from the isolated .copyclip/intelligence.db if it exists."""
    try:
        from .intelligence.db import connect, db_path
        # We need a project root context. For simplicity, we check current dir.
        root = os.getcwd()
        db = db_path(root)
        if not os.path.exists(db):
            return default
        conn = connect(root)
        row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        conn.close()
        return row[0] if row else default
    except:
        return default

_RETRIES = int(os.getenv("COPYCLIP_LLM_RETRIES", "1"))
_BACKOFF = float(os.getenv("COPYCLIP_LLM_BACKOFF", "0.75"))
_MAX_TOKENS = int(os.getenv("COPYCLIP_LLM_MAX_TOKENS", "4000"))

class HttpLLMError(Exception):
    """Custom exception for HTTP errors from an LLM API."""
    def __init__(
        self,
        *,
        status: int,
        headers: Dict[str, Any],
        body: str,
        error_code: Optional[str] = None,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        self.status = status
        self.headers = headers
        self.body = body
        self.error_code = error_code
        self.error_type = error_type
        self.error_message = error_message
        super().__init__(f"HTTP {status}: {error_message or body}")

class LLMClient(Protocol):
    """Protocol for a generic LLM client."""
    async def describe_functions(self, snippets: List[str], lang: str, system_prompt: Optional[str] = None) -> List[str]: ...
    async def minimize_code_contextually(self, code: str, file_ext: str, language: str = "en", system_prompt: Optional[str] = None) -> str: ...
    async def select_relevant_files(self, files: List[str], intent: str) -> List[str]: ...
    async def chat(self, messages: List[Dict[str, str]]) -> str: ...


# --------------------------- helpers ---------------------------

def _need(module: str, hint: str):
    """Import a module or raise a helpful error."""
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as e:
        raise RuntimeError(hint) from e

def _ensure_api_key(k: Optional[str], name: str):
    """Raise an error if an API key is missing."""
    if not k:
        raise RuntimeError(f"{name} API key not provided")

def _resolve_system_prompt(system_prompt: Optional[str]) -> Optional[tuple[str, str]]:
    """
    Resolve a system_prompt which may be a path or a literal string.

    Returns: (prompt_content, source_type ['file'|'literal']) or None.
    """
    if not system_prompt:
        return None
    try:
        if os.path.exists(system_prompt) and os.path.isfile(system_prompt):
            try:
                with open(system_prompt, "r", encoding="utf-8") as f:
                    return (f.read(), "file")
            except Exception as e:
                raise RuntimeError(f"Failed to read system_prompt file {system_prompt}: {e}") from e
    except Exception:
        # Fall through to treat as literal if os.path fails
        pass
    return (system_prompt, "literal")

def _safe_format_prompt(prompt_template: str, language: str, code_context: str) -> str:
    """Format template safely. If it has stray braces/keys, return as-is."""
    lang_name = "Spanish" if str(language).lower().startswith("es") else "English"
    try:
        return prompt_template.format(language=lang_name, code_context=code_context)
    except Exception:
        return prompt_template

def _strip_code_fences(s: str) -> str:
    """Remove ```...``` fences and leading language markers (e.g., ```json)."""
    if not s:
        return s
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()

def _normalize_lines(text: str, expected: int) -> List[str]:
    """Split into non-empty trimmed lines and pad/truncate to expected length."""
    text = _strip_code_fences(text or "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < expected:
        lines.extend([""] * (expected - len(lines)))
    elif len(lines) > expected:
        lines = lines[:expected]
    return lines

def _join_snippets(snippets: List[str]) -> str:
    """Concatenate snippets with simple headers to give structure to the model."""
    parts = []
    for i, s in enumerate(snippets, 1):
        parts.append(f"Snippet {i}:\n{s}\n")
    return "\n".join(parts)

def _iter_exc_chain(e: Optional[BaseException]) -> Iterator[BaseException]:
    """Iterate through an exception's causal chain (__cause__ or __context__)."""
    while e:
        yield e
        e = e.__cause__ or e.__context__

# Brief: map_exception_to_log_data
def map_exception_to_log_data(
    exc: Exception, *, provider: str, attempt: int, elapsed_ms: int, file_path: Optional[str] = None
) -> dict:
    """Maps an exception to a structured dictionary for logging, inspecting the full causal chain."""
    try:
        import aiohttp
    except ImportError:
        aiohttp = None  # type: ignore

    status_code: Optional[int] = None
    cause: Optional[str] = None
    retry_after_ms: Optional[int] = None
    http_exc: Optional[BaseException] = None

    # 1. Scan the causal chain for the most specific exception type first.
    for e_chain in _iter_exc_chain(exc):
        # HIGHEST PRIORITY: Configuration error before any network call is made.
        if isinstance(e_chain, ProviderConfigError):
            cause = "unauthorized" # Treat missing key as an auth issue.
            break
        if hasattr(e_chain, "status"):
            http_exc = e_chain
            break

    # 2. If an HTTP-like exception was found, classify it.
    if http_exc and cause is None:
        status_code = getattr(http_exc, "status", None)
        if status_code == 401:
            cause = "unauthorized"
        # ... (rest of the HTTP status code logic remains the same)
        elif status_code == 429:
            cause = "rate_limited"
            headers = getattr(http_exc, "headers", {}) or {}
            retry_after = headers.get("Retry-After")
            if retry_after:
                try:
                    retry_after_ms = int(float(retry_after) * 1000)
                except (ValueError, TypeError):
                    pass
        elif status_code and 500 <= status_code < 600:
            cause = "bad_response"

    # 3. If no specific cause yet, classify by other common exception types.
    if cause is None:
        for e_chain in _iter_exc_chain(exc):
            msg = str(e_chain).lower()
            if "api key not provided" in msg or "missing api key" in msg:
                cause = "unauthorized"
                break
            if isinstance(e_chain, (asyncio.TimeoutError, TimeoutError)) or \
               (aiohttp and isinstance(e_chain, aiohttp.ServerTimeoutError)):
                cause = "timeout"
                break
            if aiohttp and isinstance(e_chain, aiohttp.ClientError):
                cause = "network_error"
                break
            if isinstance(e_chain, (_json.JSONDecodeError, TypeError)):
                cause = "invalid_json"
                break

    # 3. Fallback to a generic error only if no specific cause was determined.
    if cause is None:
        cause = "llm_error"

    return {
        "message": f"minimization_failed: {cause}",
        "event": "minimization_failed",
        "file": file_path,
        "cause": cause,
        "status_code": status_code,
        "provider": provider,
        "attempt": attempt,
        "retry_after_ms": retry_after_ms,
        "elapsed_ms": elapsed_ms,
    }

# --------------------------- OpenAI ---------------------------

class OpenAIClient:
    """LLM client for OpenAI and compatible APIs."""
    def __init__(self, api_key: Optional[str], model: str, endpoint: Optional[str], timeout: int, extra_headers: Dict[str, Any] | None = None):
        self.api_key = api_key or _get_config_value("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        _ensure_api_key(self.api_key, "OpenAI")
        self.model = model or "gpt-4o-mini"
        # Permitimos base como host (/v1) o endpoint completo (/v1/chat/completions)
        self.base = (endpoint or "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout
        self.extra_headers = dict(extra_headers or {})

    def _endpoint(self, preferred: str = "chat/completions") -> str:
        if self.base.endswith("/chat/completions") or self.base.endswith("/responses"):
            return self.base
        return f"{self.base}/{preferred}"

    async def _post(self, sess, url: str, payload: dict, headers: dict) -> dict:
        """Posts a request using the modern 'max_completion_tokens' parameter."""
        payload["max_completion_tokens"] = _MAX_TOKENS
        
        async with sess.post(url, json=payload, headers=headers) as resp:
            text = await resp.text()
            if resp.ok:
                return _json.loads(text)
            
            # Levantar un error detallado en caso de fallo
            try:
                j = _json.loads(text)
                err = (j.get("error") or {})
                raise HttpLLMError(
                    status=resp.status, headers=dict(resp.headers), body=text,
                    error_code=err.get("code"), error_type=err.get("type"),
                    error_message=err.get("message")
                )
            except _json.JSONDecodeError:
                raise HttpLLMError(status=resp.status, headers=dict(resp.headers), body=text)


    async def describe_functions(self, snippets: List[str], lang: str, system_prompt: Optional[str] = None) -> List[str]:
        """Return newline-separated one-liners (≤10 words) describing each snippet."""
        aiohttp = _need("aiohttp", "Install aiohttp: pip install aiohttp")
        url = self._endpoint("chat/completions")

        # System prompt (allow override)
        default_system = (
            "For each {language} code snippet, reply with ONE short line (≤10 words) "
            "describing its purpose. Return as newline-separated lines, one per snippet. "
            "Do not add extra commentary."
        )
        system_template = _resolve_system_prompt(system_prompt)[0] if system_prompt else default_system
        system_content = _safe_format_prompt(system_template, lang, code_context="")

        user_content = _join_snippets(snippets)

        base_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", **self.extra_headers}

        start_time = time.time()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
                # LA LÍNEA MODIFICADA ES ESTA:
                data = await self._post(sess, url, base_payload, headers)

            content = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or ""
            lines = _normalize_lines(content, len(snippets))

            latency_ms = int((time.time() - start_time) * 1000)
            metrics_collector.log_llm_call(
                provider="openai",
                model=self.model,
                operation="describe_functions",
                input_text=user_content,
                output_text="\n".join(lines),
                latency_ms=latency_ms,
                cache_hit=False,
            )
            return lines

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            metrics_collector.log_llm_call(
                provider="openai",
                model=self.model,
                operation="describe_functions",
                input_text=user_content,
                output_text="",
                latency_ms=latency_ms,
                error=str(e),
            )
            raise

    async def minimize_code_contextually(self, code: str, file_ext: str, language: str = "en", system_prompt: Optional[str] = None) -> str:
        """Generate a contextually minimized version of code using LLM."""
        aiohttp = _need("aiohttp", "Install aiohttp: pip install aiohttp")
        url = self._endpoint("chat/completions")

        resolved = _resolve_system_prompt(system_prompt)
        if resolved:
            prompt_template, source = resolved
            logging.info("Using system prompt for contextual minimization (from %s)", source)
        else:
            prompt_template = "You are a helpful code analysis assistant."

        system_content = _safe_format_prompt(prompt_template, language, code_context=code)

        base_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": f"Minimize this {file_ext} code contextually:\n\n{code}"}
            ],
            "temperature": 1,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", **self.extra_headers}

        start_time = time.time()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
                data = await self._post(sess, url, base_payload, headers)

            result = (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()

            latency_ms = int((time.time() - start_time) * 1000)
            metrics_collector.log_llm_call(
                provider="openai",
                model=self.model,
                operation="minimize_contextual",
                input_text=code,
                output_text=result,
                latency_ms=latency_ms,
                cache_hit=False
            )
            return result

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            metrics_collector.log_llm_call(
                provider="openai",
                model=self.model,
                operation="minimize_contextual",
                input_text=code,
                output_text="",
                latency_ms=latency_ms,
                error=str(e)
            )
            raise

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """Generic multi-turn chat call."""
        aiohttp = _need("aiohttp", "Install aiohttp")
        url = self._endpoint("chat/completions")
        
        base_payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 1.0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", **self.extra_headers}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
            data = await self._post(sess, url, base_payload, headers)
        
        return (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()

    async def select_relevant_files(self, files: List[str], intent: str) -> List[str]:
        """Select relevant files from a list based on user intent."""
        aiohttp = _need("aiohttp", "Install aiohttp: pip install aiohttp")
        url = self._endpoint("chat/completions")

        system_content = (
            "You are a repository assistant. Given a list of files and a user's task/intent, "
            "select the most relevant files to help the user. Return ONLY a JSON list of file paths. "
            "Limit your selection to the top 10 most relevant files."
        )
        
        user_content = f"Files:\n{chr(10).join(files)}\n\nIntent: {intent}"

        base_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            "response_format": { "type": "json_object" } if "gpt-4" in self.model or "gpt-3.5" in self.model else None,
            "temperature": 0.0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", **self.extra_headers}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
            data = await self._post(sess, url, base_payload, headers)

        content = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or "[]"
        try:
            # Some models might return a wrapper object like {"files": [...]} or just [...]
            parsed = _json.loads(_strip_code_fences(content))
            if isinstance(parsed, dict):
                for k in ["files", "relevant_files", "selection"]:
                    if k in parsed and isinstance(parsed[k], list):
                        return parsed[k]
                return []
            return parsed if isinstance(parsed, list) else []
        except:
            # Fallback: look for lines that match files
            found = []
            for f in files:
                if f in content:
                    found.append(f)
            return found[:10]

# --------------------------- Anthropic ---------------------------

class AnthropicClient:
    """LLM client for Anthropic."""
    def __init__(self, api_key: Optional[str], model: str, endpoint: Optional[str], timeout: int, extra_headers: Dict[str, Any]):
        self.api_key = api_key or _get_config_value("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        _ensure_api_key(self.api_key, "Anthropic")
        self.model = model or "claude-3-5-sonnet-20240620"
        self.base = (endpoint or "https://api.anthropic.com").rstrip("/")
        self.timeout = timeout
        self.extra_headers = {"anthropic-version": "2023-06-01", **(extra_headers or {})}

    async def describe_functions(self, snippets: List[str], lang: str, system_prompt: Optional[str] = None) -> List[str]:
        """Return newline-separated one-liners (≤10 words) describing each snippet."""
        aiohttp = _need("aiohttp", "Install aiohttp: pip install aiohttp")
        url = f"{self.base}/v1/messages"

        default_system = (
            "For each {language} code snippet, reply with ONE short line (≤10 words) "
            "describing its purpose. Return as newline-separated lines, one per snippet. "
            "Do not add extra commentary."
        )
        system_template = _resolve_system_prompt(system_prompt)[0] if system_prompt else default_system
        system_content = _safe_format_prompt(system_template, lang, code_context="")

        user_content = _join_snippets(snippets)

        payload = {
            "model": self.model,
            "system": system_content,
            "messages": [{"role": "user", "content": user_content}],
            "temperature": 0.0,
            "max_tokens": _MAX_TOKENS,
        }
        headers = {"x-api-key": self.api_key, "Content-Type": "application/json", **self.extra_headers}

        start_time = time.time()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
                async with sess.post(url, json=payload, headers=headers) as resp:
                    text = await resp.text()
                    resp.raise_for_status()
                    data = _json.loads(text)

            blocks = data.get("content", [])
            content = "".join([c.get("text", "") for c in blocks]) if isinstance(blocks, list) else ""
            lines = _normalize_lines(content, len(snippets))

            latency_ms = int((time.time() - start_time) * 1000)
            metrics_collector.log_llm_call(
                provider="anthropic",
                model=self.model,
                operation="describe_functions",
                input_text=user_content,
                output_text="\n".join(lines),
                latency_ms=latency_ms,
                cache_hit=False,
            )
            return lines

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            metrics_collector.log_llm_call(
                provider="anthropic",
                model=self.model,
                operation="describe_functions",
                input_text=user_content,
                output_text="",
                latency_ms=latency_ms,
                error=str(e),
            )
            raise

    async def minimize_code_contextually(self, code: str, file_ext: str, language: str = "en", system_prompt: Optional[str] = None) -> str:
        """Generate a contextually minimized version of code using LLM."""
        aiohttp = _need("aiohttp", "Install aiohttp: pip install aiohttp")
        url = f"{self.base}/v1/messages"
        
        resolved = _resolve_system_prompt(system_prompt)
        if resolved:
            prompt_template, source = resolved
            logging.info("Using system prompt for contextual minimization (from %s)", source)
        else:
            prompt_template = "You are a helpful code analysis assistant."

        system_content = _safe_format_prompt(prompt_template, language, code_context=code)
        
        payload = {
            "model": self.model,
            "system": system_content,
            "messages": [
                {"role": "user", "content": f"Minimize this {file_ext} code contextually. Preserve all type information and add comprehensive docstrings."}
            ],
            "temperature": 0.3,
            "max_tokens": _MAX_TOKENS,
        }
        headers = {"x-api-key": self.api_key, "Content-Type": "application/json", **self.extra_headers}

        start_time = time.time()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
                async with sess.post(url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                
            result = "".join([c.get("text", "") for c in data.get("content", [])]).strip()

            latency_ms = int((time.time() - start_time) * 1000)
            metrics_collector.log_llm_call(
                provider="anthropic",
                model=self.model,
                operation="minimize_contextual",
                input_text=code,
                output_text=result,
                latency_ms=latency_ms,
                cache_hit=False
            )
            return result

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            metrics_collector.log_llm_call(
                provider="anthropic",
                model=self.model,
                operation="minimize_contextual",
                input_text=code,
                output_text="",
                latency_ms=latency_ms,
                error=str(e)
            )
            raise

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """Generic multi-turn chat call for Anthropic."""
        aiohttp = _need("aiohttp", "Install aiohttp")
        url = f"{self.base}/v1/messages"
        
        # Pull system prompt from first message if present, or keep as user
        system = ""
        user_msgs = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                user_msgs.append(m)

        payload = {
            "model": self.model,
            "system": system,
            "messages": user_msgs,
            "temperature": 1.0,
            "max_tokens": _MAX_TOKENS,
        }
        headers = {"x-api-key": self.api_key, "Content-Type": "application/json", **self.extra_headers}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
            async with sess.post(url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
        
        return "".join([c.get("text", "") for c in data.get("content", [])]).strip()


# --------------------------- DeepSeek ---------------------------

class DeepSeekClient:
    """LLM client for DeepSeek."""
    def __init__(self, api_key: Optional[str], model: str, endpoint: Optional[str], timeout: int, extra_headers: Dict[str, Any] | None = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        _ensure_api_key(self.api_key, "DeepSeek")
        self.model = model or "deepseek-coder"
        self.base = (endpoint or "https://api.deepseek.com/v1").rstrip("/")
        self.timeout = timeout
        self.extra_headers = dict(extra_headers or {})

    async def describe_functions(self, snippets: List[str], lang: str, system_prompt: Optional[str] = None) -> List[str]:
        """Return newline-separated one-liners (≤10 words) describing each snippet."""
        aiohttp = _need("aiohttp", "Install aiohttp: pip install aiohttp")
        url = f"{self.base}/chat/completions"

        default_system = (
            "For each {language} code snippet, reply with ONE short line (≤10 words) "
            "describing its purpose. Return as newline-separated lines, one per snippet. "
            "Do not add extra commentary."
        )
        system_template = _resolve_system_prompt(system_prompt)[0] if system_prompt else default_system
        system_content = _safe_format_prompt(system_template, lang, code_context="")

        user_content = _join_snippets(snippets)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.0,
            "max_tokens": _MAX_TOKENS,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", **self.extra_headers}

        timeout_cfg = aiohttp.ClientTimeout(
            total=self.timeout,
            connect=min(self.timeout, 10),
            sock_read=self.timeout,
        )

        start_time = time.time()
        
        try:
            # retry loop similar to minimize
            for attempt in range(_RETRIES + 1):
                try:
                    async with aiohttp.ClientSession(timeout=timeout_cfg) as sess:
                        async with sess.post(url, json=payload, headers=headers) as resp:
                            text = await resp.text()
                            resp.raise_for_status()
                            data = _json.loads(text)
                    break
                except asyncio.TimeoutError as e:
                    if attempt < _RETRIES:
                        await asyncio.sleep(_BACKOFF * (2 ** attempt))
                        continue
                    raise TimeoutError(f"DeepSeek request timed out after {self.timeout}s -> {url}") from e

            content = (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "") or ""
            lines = _normalize_lines(content, len(snippets))

            latency_ms = int((time.time() - start_time) * 1000)
            metrics_collector.log_llm_call(
                provider="deepseek",
                model=self.model,
                operation="describe_functions",
                input_text=user_content,
                output_text="\n".join(lines),
                latency_ms=latency_ms,
                cache_hit=False,
            )
            return lines

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            metrics_collector.log_llm_call(
                provider="deepseek",
                model=self.model,
                operation="describe_functions",
                input_text=user_content,
                output_text="",
                latency_ms=latency_ms,
                error=str(e),
            )
            raise

    async def minimize_code_contextually(self, code: str, file_ext: str, language: str = "en", system_prompt: Optional[str] = None) -> str:
        """Generate a contextually minimized version of code using LLM."""
        aiohttp = _need("aiohttp", "Install aiohttp: pip install aiohttp")
        url = f"{self.base}/chat/completions"

        resolved = _resolve_system_prompt(system_prompt)
        if resolved:
            prompt_template, source = resolved
            logging.info("Using system prompt for contextual minimization (from %s)", source)
        else:
            prompt_template = "You are a helpful code analysis assistant."

        system_content = _safe_format_prompt(prompt_template, language, code_context=code)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": f"Minimize this {file_ext} code contextually. Preserve all type information and add comprehensive docstrings."}
            ],
            "temperature": 0.3,
            "max_tokens": _MAX_TOKENS,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", **self.extra_headers}
        timeout_cfg = aiohttp.ClientTimeout(
            total=self.timeout,
            connect=min(self.timeout, 10),
            sock_read=self.timeout,
        )

        start_time = time.time()
        last_exc = None

        for attempt in range(_RETRIES + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout_cfg) as sess:
                    async with sess.post(url, json=payload, headers=headers) as resp:
                        text = await resp.text()
                        if resp.ok:
                            data = _json.loads(text)
                            result = (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
                            
                            # Log de éxito y retorno
                            latency_ms = int((time.time() - start_time) * 1000)
                            metrics_collector.log_llm_call("deepseek", self.model, "minimize_contextual", code, result, latency_ms)
                            return result
                        
                        # Si no es OK, levanta un HttpLLMError para ser capturado abajo
                        resp.raise_for_status()

            except (HttpLLMError, asyncio.TimeoutError) as e:
                last_exc = e
                is_retryable = False
                sleep_s = _BACKOFF * (2 ** attempt)

                if isinstance(e, asyncio.TimeoutError):
                    is_retryable = True
                elif isinstance(e, HttpLLMError):
                    if e.status == 429: # Rate limit
                        is_retryable = True
                        retry_after = e.headers.get("Retry-After")
                        if retry_after:
                            try:
                                sleep_s = float(retry_after)
                            except (ValueError, TypeError):
                                pass
                    elif 500 <= e.status < 600: # Error del servidor
                        is_retryable = True
                
                if is_retryable and attempt < _RETRIES:
                    logging.warning(f"API call failed (attempt {attempt+1}/{_RETRIES+1}), retrying in {sleep_s:.2f}s... Error: {e}")
                    await asyncio.sleep(sleep_s)
                    continue
                else:
                    # Si no es reintentable o se acabaron los intentos, levanta el error
                    raise e

        latency_ms = int((time.time() - start_time) * 1000)
        metrics_collector.log_llm_call(
            provider="deepseek", model=self.model, operation="minimize_contextual",
            input_text=code, output_text="", latency_ms=latency_ms, error=str(last_exc)
        )
        raise last_exc

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """Generic multi-turn chat call for DeepSeek."""
        aiohttp = _need("aiohttp", "Install aiohttp")
        url = f"{self.base}/chat/completions"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 1.0,
            "max_tokens": _MAX_TOKENS,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", **self.extra_headers}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
            async with sess.post(url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
        
        return (data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()


# --------------------------- Gemini (Google) ---------------------------

class GeminiClient:
    """LLM client for Google Gemini API."""
    def __init__(self, api_key: Optional[str], model: str, endpoint: Optional[str], timeout: int, extra_headers: Dict[str, Any] | None = None):
        self.api_key = api_key or _get_config_value("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        _ensure_api_key(self.api_key, "Gemini")
        self.model = model or "gemini-1.5-flash"
        # Endpoint structure for Gemini: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
        self.base = (endpoint or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        self.timeout = timeout
        self.extra_headers = dict(extra_headers or {})

    async def _post(self, sess, url: str, payload: dict) -> dict:
        url_with_key = f"{url}?key={self.api_key}"
        async with sess.post(url_with_key, json=payload, headers=self.extra_headers) as resp:
            text = await resp.text()
            if resp.ok:
                return _json.loads(text)
            raise HttpLLMError(status=resp.status, headers=dict(resp.headers), body=text)

    async def describe_functions(self, snippets: List[str], lang: str, system_prompt: Optional[str] = None) -> List[str]:
        aiohttp = _need("aiohttp", "Install aiohttp")
        url = f"{self.base}/models/{self.model}:generateContent"
        
        default_system = (
            "For each {language} code snippet, reply with ONE short line (≤10 words) "
            "describing its purpose. Return as newline-separated lines, one per snippet. "
            "Do not add extra commentary."
        )
        system_template = _resolve_system_prompt(system_prompt)[0] if system_prompt else default_system
        system_content = _safe_format_prompt(system_template, lang, code_context="")
        
        user_content = _join_snippets(snippets)
        
        payload = {
            "contents": [{
                "parts": [{"text": f"{system_content}\n\n{user_content}"}]
            }],
            "generationConfig": {"temperature": 0.0}
        }

        start_time = time.time()
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
                data = await self._post(sess, url, payload)
            
            content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            lines = _normalize_lines(content, len(snippets))
            return lines
        except Exception as e:
            raise e

    async def minimize_code_contextually(self, code: str, file_ext: str, language: str = "en", system_prompt: Optional[str] = None) -> str:
        aiohttp = _need("aiohttp", "Install aiohttp")
        url = f"{self.base}/models/{self.model}:generateContent"
        
        resolved = _resolve_system_prompt(system_prompt)
        system_content = _safe_format_prompt(resolved[0] if resolved else "Summarize code.", language, code_context=code)
        
        payload = {
            "contents": [{
                "parts": [{"text": f"{system_content}\n\nMinimize this {file_ext} code contextually:\n\n{code}"}]
            }],
            "generationConfig": {"temperature": 0.3}
        }

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
            data = await self._post(sess, url, payload)
        
        return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """Generic multi-turn chat call for Gemini."""
        aiohttp = _need("aiohttp", "Install aiohttp")
        url = f"{self.base}/models/{self.model}:generateContent"
        
        contents = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            # Gemini beta supports system instructions separately, but for generic we use user/model
            contents.append({
                "role": role,
                "parts": [{"text": m["content"]}]
            })

        payload = {
            "contents": contents,
            "generationConfig": {"temperature": 1.0}
        }

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
            data = await self._post(sess, url, payload)
        
        return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()

    async def select_relevant_files(self, files: List[str], intent: str) -> List[str]:
        aiohttp = _need("aiohttp", "Install aiohttp")
        url = f"{self.base}/models/{self.model}:generateContent"
        
        prompt = f"Given these files:\n{chr(10).join(files)}\n\nIntent: {intent}\n\nReturn ONLY a JSON list of relevant file paths."
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
        }

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as sess:
            data = await self._post(sess, url, payload)
        
        content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        try:
            return _json.loads(content)
        except:
            return files[:5]


# --------------------------- Factory ---------------------------

class LLMClientFactory:
    """Factory to create LLM clients based on provider."""
    @staticmethod
    def create(provider: str, *, api_key: Optional[str], model: Optional[str], endpoint: Optional[str], timeout: int, extra_headers: Dict[str, Any] | None = None) -> LLMClient:
        p = provider.lower()
        if p == "openai":
            return OpenAIClient(api_key, model, endpoint, timeout, extra_headers or {})
        if p == "anthropic":
            return AnthropicClient(api_key, model, endpoint, timeout, extra_headers or {})
        if p == "deepseek":
            return DeepSeekClient(api_key, model, endpoint, timeout, extra_headers or {})
        if p in ("gemini", "google"):
            return GeminiClient(api_key, model, endpoint, timeout, extra_headers or {})
        
        # Fallback to OpenAIClient for generic/compatible providers (OpenRouter, OpenClaw, Codex, etc.)
        logging.info(f"Provider '{provider}' unknown, falling back to OpenAI-compatible client.")
        return OpenAIClient(api_key, model, endpoint, timeout, extra_headers or {})
