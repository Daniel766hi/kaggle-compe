"""Which AI the agents think with: Claude (paid API) or a free local model through Ollama.

AI_PROVIDER=ollama or claude picks one. Without it, Claude is used when ANTHROPIC_API_KEY is set,
and the free local model otherwise. Ollama runs on your own computer (https://ollama.com):
install it, run `ollama pull qwen3:8b` once, and leave it running. OLLAMA_MODEL and OLLAMA_URL
change the model and address.
"""

import json
import os
import re

import requests

DEFAULT_OLLAMA_MODEL = "qwen3:8b"
TIMEOUT_S = 600  # local models can take minutes on a laptop


class LLMError(RuntimeError):
    pass


def provider():
    chosen = (os.environ.get("AI_PROVIDER") or "").strip().lower()
    if chosen in ("claude", "ollama"):
        return chosen
    return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "ollama"


def ollama_url():
    return (os.environ.get("OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")


def ollama_model():
    return os.environ.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL


def web_search_available():
    """Only Claude can search the web; the local model writes from the profile alone."""
    return provider() == "claude"


def available(session=None):
    """Whether the chosen AI can be reached from here (Ollama isn't running on GitHub's servers)."""
    if provider() == "claude":
        return True
    try:
        (session or requests).get(f"{ollama_url()}/api/tags", timeout=3).raise_for_status()
        return True
    except requests.RequestException:
        return False


def ollama_chat(messages, tools=None, schema=None, session=None):
    """One /api/chat call. Returns Ollama's assistant message (content, maybe tool_calls)."""
    body = {"model": ollama_model(), "messages": messages, "stream": False}
    if tools:
        body["tools"] = tools
    if schema:
        body["format"] = schema
    try:
        resp = (session or requests).post(f"{ollama_url()}/api/chat", json=body, timeout=TIMEOUT_S)
    except requests.ConnectionError as e:
        raise LLMError(f"Ollama isn't running at {ollama_url()}. Start the Ollama app (or `ollama serve`).") from e
    if resp.status_code == 404:
        raise LLMError(f"The model {ollama_model()} isn't installed. Run: ollama pull {ollama_model()}")
    if resp.status_code >= 400:
        raise LLMError(f"Ollama error {resp.status_code}: {resp.text[:300]}")
    return resp.json()["message"]


def ollama_json(system, request, schema, session=None):
    """Ask the local model for an answer that matches a JSON schema."""
    message = ollama_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": request}], schema=schema, session=session
    )
    answer = strip_thinking(message.get("content", ""))
    try:
        return json.loads(answer)
    except json.JSONDecodeError as e:
        raise LLMError(f"could not read the local model's answer as JSON: {answer[:300]!r}") from e


def strip_thinking(text):
    """Older Ollama versions leave a model's <think>...</think> reasoning in the answer."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
