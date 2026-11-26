"""All Gemini calls go through here: one queue, retries, structured JSON output."""
import json
import threading
import time

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Only 2 Gemini calls at a time -> stays inside free-tier rate limits
_queue = threading.Semaphore(2)


class GeminiError(Exception):
    pass


def _call(contents, config):
    if not client:
        raise GeminiError("GEMINI_API_KEY is missing in backend/.env")
    last = None
    for attempt in range(3):
        try:
            with _queue:
                return client.models.generate_content(model=GEMINI_MODEL, contents=contents,
                                                      config=config)
        except Exception as e:
            last = e
            msg = str(e)
            wait = 2 ** attempt * (8 if "429" in msg or "RESOURCE_EXHAUSTED" in msg else 1)
            time.sleep(wait)
    raise GeminiError(f"Gemini failed after 3 tries: {last}")


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
