"""Student-facing coordinator agent built with Google ADK (text chat).
Uses the same tools as the voice agent. Falls back to plain Gemini function calling if ADK fails."""
import functools

from google.genai import types

from activity_log import log
from agents.assistant_tools import ALL_TOOLS, SYSTEM_INSTRUCTION
from config import GEMINI_MODEL

APP = "studypilot"
USER = "student"


def _logged(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        log("Coordinator", f"🛠 Tool call: {fn.__name__}({', '.join(map(str, kwargs.values()))})")
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log("Coordinator", f"Tool {fn.__name__} failed: {e}", "error")
            return {"error": str(e)}
    return wrapper


TOOLS = [_logged(f) for f in ALL_TOOLS]

try:
    from google.adk.agents import Agent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    root_agent = Agent(name="studypilot_coordinator", model=GEMINI_MODEL,
                       description="Coordinates StudyPilot's tutor and planner tools.",
                       instruction=SYSTEM_INSTRUCTION, tools=TOOLS)
    runner = Runner(app_name=APP, agent=root_agent, session_service=InMemorySessionService(),
                    auto_create_session=True)
    ADK_OK = True
except Exception as e:  # pragma: no cover
    print("ADK unavailable, using plain Gemini:", e)
    ADK_OK = False


async def chat(message: str, session_id: str = "default") -> str:
    if ADK_OK:
        try:
            content = types.Content(role="user", parts=[types.Part(text=message)])
            reply = ""
            async for event in runner.run_async(user_id=USER, session_id=session_id,
                                                new_message=content):
                if event.content and event.content.parts and event.is_final_response():
                    reply = "".join(p.text or "" for p in event.content.parts)
            return reply or "Done."
        except Exception as e:
            log("Coordinator", f"Main agent model busy ({type(e).__name__}) — switching to backup "
                               "model.", "warn")
    # Fallback: google-genai automatic function calling, trying each backup model
    import asyncio
    from gemini import client
    from config import MODEL_CHAIN
    cfg = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION, tools=TOOLS)
    last = None
    for model in MODEL_CHAIN[1:] or MODEL_CHAIN:
        try:
            resp = await asyncio.to_thread(client.models.generate_content, model=model,
                                           contents=message, config=cfg)
            return resp.text or "Done."
        except Exception as e:
            last = e
    return f"Sorry, Gemini is overloaded right now ({last}). Try again in a moment."
