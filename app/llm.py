"""LLM client: local Ollama by default, or any OpenAI-compatible API.

Default is Ollama (nothing leaves the machine). For free hosted deployment without
a local GPU, set LLM_PROVIDER=openai and point OPENAI_BASE_URL/OPENAI_API_KEY at a
compatible provider (e.g. Groq free tier).
"""
import os
import time

import httpx

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:3b")
TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "120"))

_status_cache = {"at": 0.0, "value": None}


def _use_openai() -> bool:
    return LLM_PROVIDER in ("openai", "groq", "openai-compatible")


def status(force=False) -> dict:
    """Is the configured model reachable? Cached for 15 s."""
    if not force and time.time() - _status_cache["at"] < 15 and _status_cache["value"]:
        return _status_cache["value"]

    if _use_openai():
        val = {"online": bool(OPENAI_API_KEY), "model": LLM_MODEL, "url": OPENAI_BASE_URL, "detail": ""}
        if not OPENAI_API_KEY:
            val["detail"] = "OPENAI_API_KEY is not set"
        else:
            try:
                r = httpx.get(f"{OPENAI_BASE_URL}/models", headers=_openai_headers(), timeout=5)
                if r.status_code == 200:
                    val["online"] = True
                else:
                    val["online"] = True  # key is set; some providers restrict /models
                    val["detail"] = f"/models returned {r.status_code}; chat may still work"
            except Exception:  # noqa: BLE001
                val["online"] = True
                val["detail"] = "Could not verify /models; chat may still work"
        _status_cache.update(at=time.time(), value=val)
        return val

    val = {"online": False, "model": LLM_MODEL, "url": OLLAMA_URL, "detail": ""}
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        names = [m["name"] for m in r.json().get("models", [])]
        base = LLM_MODEL if ":" in LLM_MODEL else LLM_MODEL + ":latest"
        if base in names or LLM_MODEL in names:
            val["online"] = True
        else:
            val["detail"] = f"Ollama is running but model '{LLM_MODEL}' is not pulled yet"
    except Exception:  # noqa: BLE001
        val["detail"] = f"Ollama not reachable at {OLLAMA_URL}"
    _status_cache.update(at=time.time(), value=val)
    return val


def _openai_headers() -> dict:
    return {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}


def chat(system: str, user: str, temperature=0.1, max_tokens=500, json_mode=False) -> str:
    if _use_openai():
        body = {
            "model": LLM_MODEL,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = httpx.post(f"{OPENAI_BASE_URL}/chat/completions", headers=_openai_headers(), timeout=TIMEOUT, json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    body = {
        "model": LLM_MODEL,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 4096},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if json_mode:
        body["format"] = "json"
    if LLM_MODEL.startswith("qwen3"):
        body["think"] = False  # answer directly, no long hidden reasoning
    r = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=TIMEOUT, json=body)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()
