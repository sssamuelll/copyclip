# graph TD;
# src/copyclip/tokens.py
from typing import Optional, Tuple
# Brief: _get_encoding
# Brief: _get_encoding

# Brief: _get_encoding
def _get_encoding(encoding_preference: Optional[str], model: Optional[str]):
    """
    
        Devuelve (encoding, source_name, exact, tiktoken_module|None).
        - Si pasas model (ej. 'gpt-4o'), intenta encoding_for_model(model).
        - Si pasas encoding_preference (ej. 'o200k_base'), lo usa.
        - Si nada, intenta o200k_base y luego cl100k_base.
    Args:
        TODO: describe arguments
    """
    try:
        import tiktoken
        if model:
            try:
                enc = tiktoken.encoding_for_model(model)
                return enc, enc.name, True, tiktoken
            except Exception:
                ...
        if encoding_preference:
            try:
                enc = tiktoken.get_encoding(encoding_preference)
                return enc, encoding_preference, True, tiktoken
            except Exception:
                ...
        try:
            enc = tiktoken.get_encoding("o200k_base")
            return enc, "o200k_base", True, tiktoken
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
            return enc, "cl100k_base", True, tiktoken
    except Exception:
        return None, (encoding_preference or model or "approx_4char"), False, None
# Brief: analyze_context_windows

# Brief: analyze_context_windows
def analyze_context_windows(token_count):
    """
    Analyze if content fits within popular model context windows.
    
    Args:
        token_count: Number of tokens in the content
        
    Returns:
        String with analysis results
    """
    models = {
        "GPT-5": 32000,
        "Claude": 200000
    }
    
    results = []
    
    for model_name, context_limit in models.items():
        if token_count <= context_limit:
            percentage = (token_count / context_limit) * 100
            results.append(f"✅ {model_name} ({context_limit:,}): {percentage:.1f}% used")
        else:
            overflow = token_count - context_limit
            results.append(f"❌ {model_name} ({context_limit:,}): exceeds by {overflow:,} tokens")
    
    return "\n".join([f"[INFO] {result}" for result in results])
# Brief: count_raw_tokens

# Brief: count_raw_tokens
def count_raw_tokens(text: str, encoding_preference: Optional[str] = None, model: Optional[str] = None) -> Tuple[int, str, bool]:
    """
    
        Cuenta tokens del texto TAL CUAL (sin ChatML), usando tiktoken si está disponible.
        Retorna (count, source, exact).
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    enc, source, exact, _ = _get_encoding(encoding_preference, model)
    if enc is not None:
        try:
            return len(enc.encode(text)), source, True
        except Exception:
            ...
    approx = (len(text) + 3) // 4  # ~1 token por 4 chars
    return approx, "approx_4char", False

# Brief: count_chat_tokens

# Brief: count_chat_tokens
def count_chat_tokens(text: str, model: Optional[str]) -> Tuple[int, str, bool]:
    """
    
        Cuenta tokens como **un solo mensaje de usuario** para el modelo dado (ChatGPT),
        aplicando el chat template (ChatML) del modelo.
        Retorna (count, source=model, exact).
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    enc, source, exact, tk = _get_encoding(None, model)
    if enc is not None and tk is not None and model:
        try:
            messages = [{"role": "user", "content": text}]
            # Requiere tiktoken>=0.5 con chat templates
            rendered = enc.apply_chat_template(messages, tokenize=False, add_special_tokens=True)
            return len(enc.encode(rendered)), model, True
        except Exception:
            # Fallback: cuenta sin template pero con el encoding del modelo
            try:
                return len(enc.encode(text)), source, True
            except Exception:
                ...
    approx = (len(text) + 3) // 4
    return approx, "approx_4char", False
