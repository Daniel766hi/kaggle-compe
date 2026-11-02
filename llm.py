"""Which AI the agents think with: Claude (paid API), Gemini (free API key) or a free local model.

AI_PROVIDER=claude, gemini or ollama picks one. Without it: Claude when ANTHROPIC_API_KEY is set,
else Gemini when GEMINI_API_KEY is set, else the local model.

- Gemini: a free key from https://aistudio.google.com/apikey (no card). It runs in Google's cloud,
  so the office works from a phone, GitHub's servers or any computer. GEMINI_MODEL changes the
  model (default gemini-flash-latest, a free one). When Gemini is over its free limit, the office
  switches by itself to Gemini's lighter model, then to any other free AI you added a key for
  (GROQ_API_KEY from console.groq.com, OPENROUTER_API_KEY from openrouter.ai, CEREBRAS_API_KEY
  from cloud.cerebras.ai), then to Ollama if it runs on this computer.
- Ollama runs on your own computer (https://ollama.com): install it, run `ollama pull qwen3:8b`
  once, and leave it running. OLLAMA_MODEL and OLLAMA_URL change the model and address.
"""

import json
import logging
import os
import re
import time

import requests

DEFAULT_OLLAMA_MODEL = "qwen3:8b"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
DEFAULT_GEMINI_FALLBACK = "gemini-flash-lite-latest"
TIMEOUT_GEMINI = (15, 150)  # seconds to connect, seconds to wait for the answer
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
TIMEOUT_S = 600  # local models can take minutes on a laptop
RETRY_WAITS_S = (5, 20, 40)  # Gemini's free tier allows a few requests a minute
# More free AIs the office switches to when Gemini is over its limit: key, OpenAI-compatible URL,
# setting for the model, default model. All are optional; each has its own free daily limit.
FREE_CLOUDS = {
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1", "GROQ_MODEL", "openai/gpt-oss-120b"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "OPENROUTER_MODEL", "openai/gpt-oss-120b:free"),
    "cerebras": ("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1", "CEREBRAS_MODEL", "gpt-oss-120b"),
}
_resting = {}  # (provider, model) -> when it may be asked again
_ollama_seen = {}


class LLMError(RuntimeError):
    pass


def provider():
    chosen = (os.environ.get("AI_PROVIDER") or "").strip().lower()
    if chosen in ("claude", "gemini", "ollama"):
        return chosen
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    cloud = ("GEMINI_API_KEY", *(key for key, *_ in FREE_CLOUDS.values()))
    return "gemini" if any(os.environ.get(k) for k in cloud) else "ollama"  # "gemini": the free cloud AIs


def gemini_model():
    return os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL


def describe():
    """Which AI the team thinks with, in a few words."""
    if provider() == "gemini":
        names = list(dict.fromkeys(name for name, *_ in cloud_targets()))
        return "free AIs: " + ", then ".join(n.capitalize() for n in names)
    return {"claude": "Claude"}.get(provider(), f"{ollama_model()} on this computer (free)")


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


def cloud_targets():
    """The free AIs to try, in order: (name, base URL, key, model). Ollama on this computer comes last."""
    targets = []
    if os.environ.get("GEMINI_API_KEY"):
        for model in dict.fromkeys([gemini_model(), os.environ.get("GEMINI_FALLBACK_MODEL") or DEFAULT_GEMINI_FALLBACK]):
            targets.append(("gemini", GEMINI_URL, os.environ["GEMINI_API_KEY"], model))
    for name, (key_env, url, model_env, model) in FREE_CLOUDS.items():
        if os.environ.get(key_env):
            targets.append((name, url, os.environ[key_env], os.environ.get(model_env) or model))
    if os.environ.get("AI_LOCAL_FALLBACK", "on") != "off" and _ollama_up():
        targets.append(("ollama", f"{ollama_url()}/v1", "ollama", ollama_model()))
    return targets


def gemini_chat(messages, tools=None, schema=None, session=None, sleep=time.sleep):
    """One chat call to the free cloud AIs (Gemini first). Returns the assistant message.

    When one is over its free limit, too slow, overloaded or doesn't know the model, the next one
    answers (Gemini's lighter model, then Groq, OpenRouter, Cerebras, then Ollama on this
    computer). A provider over its limit is skipped for a while (a minute, or an hour for a
    daily limit), so the office doesn't keep asking it. Gemini is asked for short thinking
    (GEMINI_THINKING, default low) so answers come in seconds.
    """
    targets = cloud_targets()
    if not targets:
        raise LLMError("No free AI key is set. Get a free Gemini key at https://aistudio.google.com/apikey")
    tried, now = [], time.monotonic()
    for name, url, key, model in targets:
        if _resting.get((name, model), 0) > now:
            tried.append(f"{name} (resting)")
            continue
        try:
            return _openai_chat(name, url, key, model, messages, tools, schema, session, sleep)
        except _TryNext as e:
            _resting[(name, model)] = time.monotonic() + e.rest_s
            logging.warning("%s %s: %s; trying the next free AI", name, model, e)
            tried.append(f"{name}: {e}")
    raise LLMError("The free AI limits are used up for now (" + "; ".join(tried) + "). Try again in a few minutes, "
                   "or add another free key (GROQ_API_KEY, OPENROUTER_API_KEY) so the office can switch.")  # fmt: skip


class _TryNext(Exception):
    def __init__(self, message, rest_s=0):
        super().__init__(message)
        self.rest_s = rest_s


def _openai_chat(name, url, key, model, messages, tools, schema, session, sleep):
    if name != "gemini":  # Gemini's thought signatures mean nothing to the others
        messages = [_without_extras(m) for m in messages]
    body = {"model": model, "messages": messages}
    thinking = (os.environ.get("GEMINI_THINKING") or "low").strip().lower()
    if name == "gemini" and thinking != "default":
        body["reasoning_effort"] = thinking
    if tools:
        body["tools"] = [{**t, "function": {**t["function"], "parameters": _plain(t["function"]["parameters"])}} for t in tools]
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "schema": _plain(schema)}}
    headers = {"Authorization": f"Bearer {key}"}
    timeout = TIMEOUT_S if name == "ollama" else TIMEOUT_GEMINI
    post = (session or requests).post
    try:
        resp = post(f"{url}/chat/completions", json=body, headers=headers, timeout=timeout)
        if resp.status_code == 429:  # often only the per-minute limit: one short wait
            sleep(RETRY_WAITS_S[0])
            resp = post(f"{url}/chat/completions", json=body, headers=headers, timeout=timeout)
        if resp.status_code == 400 and "reasoning" in resp.text.lower() and "reasoning_effort" in body:
            body.pop("reasoning_effort")  # a model without thinking settings
            resp = post(f"{url}/chat/completions", json=body, headers=headers, timeout=timeout)
        if resp.status_code == 400 and schema and ("response_format" in resp.text or "json_schema" in resp.text):
            body["response_format"] = {"type": "json_object"}  # no structured output here: ask for JSON in words
            body["messages"] = [*messages, {"role": "system", "content": "Answer with JSON only, matching this schema: "
                                            + json.dumps(_plain(schema))}]  # fmt: skip
            resp = post(f"{url}/chat/completions", json=body, headers=headers, timeout=timeout)
    except requests.Timeout as e:
        raise _TryNext("didn't answer in time", 60) from e
    except requests.RequestException as e:
        raise _TryNext(f"couldn't be reached ({type(e).__name__})", 60) from e
    text = resp.text.lower()
    if resp.status_code == 429:
        daily = any(w in text for w in ("per day", "daily", "per-day", "quota exceeded", "rpd", "tpd"))
        raise _TryNext("over its free limit", 3600 if daily else 60)
    if resp.status_code in (401, 403) or (resp.status_code == 400 and "api key" in text):
        raise _TryNext(f"didn't accept its key ({_key_env(name)})", 3600)
    if resp.status_code == 404:
        raise _TryNext(f"has no model {model!r}", 3600)
    if resp.status_code >= 500:
        raise _TryNext("is overloaded", 60)
    if resp.status_code >= 400:
        raise _TryNext(f"error {resp.status_code}: {resp.text[:200]}", 60)
    return resp.json()["choices"][0]["message"]


def _without_extras(message):
    if not message.get("tool_calls"):
        return message
    calls = [{k: v for k, v in call.items() if k != "extra_content"} for call in message["tool_calls"]]
    return {**message, "tool_calls": calls}


def _key_env(name):
    return "GEMINI_API_KEY" if name == "gemini" else FREE_CLOUDS.get(name, ("Ollama",))[0]


def _ollama_up():
    """Whether Ollama runs on this computer (remembered for a minute)."""
    now = time.monotonic()
    if _ollama_seen.get("until", 0) < now:
        try:
            requests.get(f"{ollama_url()}/api/tags", timeout=2).raise_for_status()
            _ollama_seen.update(up=True)
        except requests.RequestException:
            _ollama_seen.update(up=False)
        _ollama_seen["until"] = now + 60
    return _ollama_seen["up"]


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


if __name__ == "__main__":  # python -m llm: check that the AI answers, and how fast
    import local_env

    local_env.load()
    print(f"AI: {describe()}")
    started = time.monotonic()
    try:
        reply = chat([{"role": "user", "content": "Reply with just the word: ready"}])
        print(f"Answer: {strip_thinking(reply.get('content') or '')!r} in {time.monotonic() - started:.1f} s")
    except LLMError as e:
        print(f"Failed after {time.monotonic() - started:.1f} s: {e}")
