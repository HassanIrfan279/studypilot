"""All Gemini calls go through here: one queue, retries, structured JSON output."""
import json
import threading
import time

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, MODEL_CHAIN

# 90s timeout per call so a stuck request can never freeze the demo
client = (genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=60_000))
          if GEMINI_API_KEY else None)

# Only 2 Gemini calls at a time -> stays inside free-tier rate limits
_queue = threading.Semaphore(2)


class GeminiError(Exception):
    pass


def _busy(e):
    msg = str(e)
    return any(s in msg for s in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "overloaded",
                                  "504", "DEADLINE", "timed out", "Timeout", "404"))


def _call(contents, config):
    """Try the main model; if Google says it's busy, fall back to the next model in the list."""
    if not client:
        raise GeminiError("GEMINI_API_KEY is missing in backend/.env")
    last = None
    for model in MODEL_CHAIN:
        for attempt in range(2):
            try:
                with _queue:
                    return client.models.generate_content(model=model, contents=contents,
                                                          config=config)
            except Exception as e:
                last = e
                if _busy(e):
                    break  # this model is overloaded -> try the next one right away
                time.sleep(2 ** attempt)
    raise GeminiError(f"Gemini failed on all models: {last}")


def file_part(data: bytes, mime: str):
    return types.Part.from_bytes(data=data, mime_type=mime)


def generate_json(prompt: str, schema, parts=None, system=None) -> dict:
    """Ask Gemini for JSON matching a Pydantic `schema`. Re-asks once if the JSON is bad."""
    contents = list(parts or []) + [prompt]
    config = types.GenerateContentConfig(response_mime_type="application/json",
                                         response_schema=schema, system_instruction=system,
                                         temperature=0.4)
    for strict in (False, True):
        if strict:
            contents = list(parts or []) + [
                prompt + "\n\nIMPORTANT: Reply with ONLY valid JSON matching the schema. No prose."]
        resp = _call(contents, config)
        try:
            if resp.parsed is not None:
                return resp.parsed.model_dump() if hasattr(resp.parsed, "model_dump") else resp.parsed
            return json.loads(resp.text)
        except Exception:
            continue
    raise GeminiError("Gemini returned invalid JSON twice.")


def generate_text(prompt: str, parts=None, system=None) -> str:
    config = types.GenerateContentConfig(system_instruction=system, temperature=0.6)
    resp = _call(list(parts or []) + [prompt], config)
    return (resp.text or "").strip()
