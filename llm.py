import requests

from config import get_settings


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    pass


class LLMTimeout(LLMError):
    pass


class LLMInvalidOutput(LLMError):
    pass


def _chat(system: str, user: str, json_mode: bool, max_tokens: int) -> str:
    s = get_settings()
    payload = {
        "model": s.ollama_model,
        "stream": False,
        "keep_alive": "10m",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": max_tokens},
    }
    if json_mode:
        payload["format"] = "json"
    try:
        resp = requests.post(s.ollama_base_url.rstrip("/") + "/api/chat", json=payload, timeout=s.ollama_timeout)
    except requests.Timeout as exc:
        raise LLMTimeout(f"Ollama did not answer within {s.ollama_timeout}s.") from exc
    except requests.ConnectionError as exc:
        raise LLMUnavailable("Ollama is not running at " + s.ollama_base_url) from exc
    if resp.status_code == 404:
        raise LLMUnavailable(f"Model '{s.ollama_model}' not found. Run: ollama pull {s.ollama_model}")
    if resp.status_code != 200:
        raise LLMUnavailable(f"Ollama returned HTTP {resp.status_code}.")
    try:
        content = resp.json()["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise LLMInvalidOutput("Unexpected response shape from Ollama.") from exc
    if not content or not content.strip():
        raise LLMInvalidOutput("Ollama returned an empty answer.")
    return content


def chat_json(system: str, user: str) -> str:
    return _chat(system, user, json_mode=True, max_tokens=200)


def chat_text(system: str, user: str) -> str:
    return _chat(system, user, json_mode=False, max_tokens=400)


def ollama_status() -> dict:
    """For the UI sidebar: is Ollama up and is the model pulled?"""
    s = get_settings()
    try:
        resp = requests.get(s.ollama_base_url.rstrip("/") + "/api/tags", timeout=3)
        names = [m.get("name", "") for m in resp.json().get("models", [])]
    except (requests.RequestException, ValueError):
        return {"running": False, "model_ready": False, "model": s.ollama_model}
    ready = any(n == s.ollama_model or n.split(":")[0] == s.ollama_model for n in names)
    return {"running": True, "model_ready": ready, "model": s.ollama_model}
