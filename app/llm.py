"""Thin client for a local Ollama server. Nothing leaves the machine."""
import os
import time

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:3b")
TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "120"))

_status_cache = {"at": 0.0, "value": None}


def status(force=False) -> dict:
    """Is the local model reachable and pulled? Cached for 15 s."""
    if not force and time.time() - _status_cache["at"] < 15 and _status_cache["value"]:
        return _status_cache["value"]
    val = {"online": False, "model": LLM_MODEL, "url": OLLAMA_URL, "detail": ""}
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        names = [m["name"] for m in r.json().get("models", [])]
        base = LLM_MODEL if ":" in LLM_MODEL else LLM_MODEL + ":latest"
        if base in names or LLM_MODEL in names:
            val["online"] = True
        else:
            val["detail"] = f"Ollama is running but model '{LLM_MODEL}' is not pulled yet"
    except Exception as e:  # noqa: BLE001
        val["detail"] = f"Ollama not reachable at {OLLAMA_URL}"
    _status_cache.update(at=time.time(), value=val)
    return val


def chat(system: str, user: str, temperature=0.1, max_tokens=500, json_mode=False) -> str:
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
