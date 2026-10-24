"""Which AI the agents think with: Claude (paid API), Gemini (free API key) or a free local model.

AI_PROVIDER=claude, gemini or ollama picks one. Without it: Claude when ANTHROPIC_API_KEY is set,
else Gemini when GEMINI_API_KEY is set, else the local model.

- Gemini: a free key from https://aistudio.google.com/apikey (no card). It runs in Google's cloud,
  so the office works from a phone, GitHub's servers or any computer. GEMINI_MODEL changes the
  model (default gemini-flash-latest, a free one).
- Ollama runs on your own computer (https://ollama.com): install it, run `ollama pull qwen3:8b`
  once, and leave it running. OLLAMA_MODEL and OLLAMA_URL change the model and address.
"""

import json
import os
import re
import time

import requests

DEFAULT_OLLAMA_MODEL = "qwen3:8b"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
TIMEOUT_S = 600  # local models can take minutes on a laptop
RETRY_WAITS_S = (5, 20, 40)  # Gemini's free tier allows a few requests a minute


class LLMError(RuntimeError):
    pass


def provider():
    chosen = (os.environ.get("AI_PROVIDER") or "").strip().lower()
    if chosen in ("claude", "gemini", "ollama"):
        return chosen
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    return "gemini" if os.environ.get("GEMINI_API_KEY") else "ollama"


def gemini_model():
    return os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL


def describe():
    """Which AI the team thinks with, in a few words."""
    return {"claude": "Claude", "gemini": f"Gemini ({gemini_model()}, free key)"}.get(
        provider(), f"{ollama_model()} on this computer (free)"
    )


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
    if provider() == "gemini":
        return bool(os.environ.get("GEMINI_API_KEY"))
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


def gemini_chat(messages, tools=None, schema=None, session=None, sleep=time.sleep):
    """One chat call to Gemini's OpenAI-compatible API. Returns the assistant message."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise LLMError("GEMINI_API_KEY isn't set. Get a free key at https://aistudio.google.com/apikey")
    body = {"model": gemini_model(), "messages": messages}
    if tools:
        body["tools"] = [{**t, "function": {**t["function"], "parameters": _plain(t["function"]["parameters"])}} for t in tools]
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "schema": _plain(schema)}}
    headers = {"Authorization": f"Bearer {key}"}
    for wait in (*RETRY_WAITS_S, None):
        try:
            resp = (session or requests).post(f"{GEMINI_URL}/chat/completions", json=body, headers=headers, timeout=300)
        except requests.RequestException as e:
            raise LLMError(f"Couldn't reach Gemini: {e}") from e
        if resp.status_code not in (429, 500, 503) or wait is None:
            break
        sleep(wait)  # busy or over the per-minute limit: wait and try again
    if resp.status_code == 429:
        raise LLMError("Gemini's free limit is used up for now. Try again in a minute (or tomorrow, if it's the daily limit).")
    if resp.status_code in (400, 401, 403) and "key" in resp.text.lower():
        raise LLMError("Gemini didn't accept GEMINI_API_KEY. Copy it again from https://aistudio.google.com/apikey")
    if resp.status_code == 404:
        raise LLMError(f"Gemini has no model {gemini_model()!r}. Set GEMINI_MODEL to one listed in Google AI Studio.")
    if resp.status_code >= 400:
        raise LLMError(f"Gemini error {resp.status_code}: {resp.text[:300]}")
    return resp.json()["choices"][0]["message"]


def chat(messages, tools=None, schema=None, session=None):
    """One call to the free AI that is chosen (Gemini or the local model)."""
    if provider() == "gemini":
        return gemini_chat(messages, tools, schema, session)
    return ollama_chat(messages, tools, schema, session)


def json_answer(system, request, schema, session=None):
    """Ask the free AI for an answer that matches a JSON schema."""
    message = chat([{"role": "system", "content": system}, {"role": "user", "content": request}], schema=schema, session=session)
    answer = strip_thinking(message.get("content") or "")
    answer = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer)  # some models wrap JSON in a code fence
    try:
        return json.loads(answer)
    except json.JSONDecodeError as e:
        raise LLMError(f"could not read the AI's answer as JSON: {answer[:300]!r}") from e



def _plain(schema):
    """The schema without the strict-mode extras Gemini doesn't take."""
    if isinstance(schema, dict):
        return {k: _plain(v) for k, v in schema.items() if k not in ("additionalProperties", "strict")}
    if isinstance(schema, list):
        return [_plain(v) for v in schema]
    return schema


def strip_thinking(text):
    """Older Ollama versions leave a model's <think>...</think> reasoning in the answer."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
