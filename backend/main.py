"""StudyPilot backend: FastAPI routes + WebSockets. Run with:  uvicorn main:app --reload --port 8000"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

import activity_log
import auth
import db
import scheduler
from activity_log import log
from agents import chat_agent, planner_agent, voice_agent
from config import FRONTEND_URL, TIMEZONE
from google_clients import NotLoggedIn
from tools import calendar_tools as cal
from tools import study_tools as st


@asynccontextmanager
async def lifespan(app):
    activity_log.set_loop(asyncio.get_running_loop())
    task = asyncio.create_task(scheduler.loop())
    yield
    task.cancel()


app = FastAPI(title="StudyPilot", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[FRONTEND_URL, "http://127.0.0.1:5173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(NotLoggedIn)
async def not_logged_in(_, exc):
    return JSONResponse({"error": str(exc)}, status_code=401)


@app.exception_handler(Exception)
async def any_error(_, exc):
    log("Coordinator", f"Something went wrong: {exc}", "error")
    return JSONResponse({"error": str(exc)}, status_code=500)


def run(fn, *a, **kw):
    """Run blocking Google/Gemini code without freezing the server."""
    return asyncio.to_thread(fn, *a, **kw)


# ---------- health + auth ----------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/login")
def login():
    return RedirectResponse(auth.login_url())


@app.get("/auth/callback")
async def callback(request: Request, state: str = ""):
    await run(auth.handle_callback, str(request.url), state)
    log("Coordinator", "✅ Signed in with Google. Starting first sync…", "success")
    asyncio.create_task(run(scheduler.sync_once, True))
    return RedirectResponse(FRONTEND_URL)


@app.post("/auth/logout")
def logout():
    auth.logout()
    return {"ok": True}


@app.get("/api/me")
async def me():
    creds = await run(auth.get_credentials)
    return {"logged_in": bool(creds), "last_sync": db.kv_get("last_sync")}


# ---------- dashboard ----------
def _courses():
    rows = db.query("SELECT * FROM courses ORDER BY name")
    for r in rows:
        r["color_hex"] = cal.COLOR_HEX[cal.course_color(r["id"])]
    return rows


@app.get("/api/dashboard")
async def dashboard():
    items = await run(st.upcoming_items, 30)
    colors = {c["id"]: c["color_hex"] for c in _courses()}
    for i in items:
        i["color"] = colors.get(i["course_id"], "#3f51b5")
        i["priority"] = planner_agent.priority_score(i)
    return {"items": items, "courses": _courses(), "last_sync": db.kv_get("last_sync")}


@app.post("/api/sync")
async def sync_now():
    return await run(scheduler.sync_once, True)


@app.get("/api/activity")
def activity():
    return activity_log.recent(150)


@app.get("/api/brief")
async def brief(refresh: bool = False):
    return await run(st.daily_brief, refresh)


# ---------- courses + lectures ----------
@app.get("/api/courses/{course_id}")
def course(course_id: str):
    c = db.one("SELECT * FROM courses WHERE id=?", (course_id,))
    items = db.query("SELECT * FROM items WHERE course_id=? AND active=1 ORDER BY due", (course_id,))
    mats = db.query("SELECT * FROM materials WHERE course_id=? ORDER BY created DESC", (course_id,))
    for m in mats:
        m["analyzed"] = db.cache_get(f"analysis:{m['file_id']}") is not None
    return {"course": c, "items": items, "materials": mats}


@app.get("/api/lectures/{file_id}")
async def lecture(file_id: str):
    return await run(st.analyze_lecture, file_id)


class TextIn(BaseModel):
    text: str


@app.post("/api/urdu")
async def urdu(body: TextIn):
    return {"urdu": await run(st.explain_in_urdu, body.text)}


# ---------- prep packs, quizzes, panic ----------
@app.get("/api/prep/{assessment_id}")
async def prep(assessment_id: str, refresh: bool = False):
    pack = await run(st.build_prep_pack, assessment_id, refresh)
    if pack:
        pack["readiness"] = st.readiness(assessment_id)
    return pack


class ScoreIn(BaseModel):
    score: float  # 0..1


@app.post("/api/quiz/{assessment_id}/result")
def quiz_result(assessment_id: str, body: ScoreIn):
    st.save_quiz_result(assessment_id, body.score)
    activity_log.refresh()
    return st.readiness(assessment_id)


@app.get("/api/panic/{assessment_id}")
async def panic(assessment_id: str, minutes: int = 120):
    return await run(st.panic_mode, assessment_id, minutes)


# ---------- plan ----------
@app.get("/api/plan")
async def plan():
    now = datetime.now(ZoneInfo(TIMEZONE)).isoformat()
    sessions = db.query("SELECT s.*, i.course_id, i.title AS assessment_title FROM sessions s "
                        "LEFT JOIN items i ON i.id=s.assessment_id ORDER BY s.start")
    colors = {c["id"]: c["color_hex"] for c in _courses()}
    for s in sessions:
        s["color"] = colors.get(s["course_id"], "#3f51b5")
        s["past"] = s["end"] < now
    priorities = await run(planner_agent.prioritize)
    return {"sessions": sessions,
            "priorities": [{"id": p["id"], "title": p["title"], "course_name": p["course_name"],
                            "priority": p["priority"], "due": p["due"]} for p in priorities]}


@app.post("/api/plan/all")
async def plan_all():
    await run(planner_agent.plan_unplanned)
    activity_log.refresh()
    return {"ok": True}


@app.post("/api/plan/{assessment_id}/replan")
async def replan(assessment_id: str):
    res = await run(planner_agent.replan, assessment_id, "student asked")
    activity_log.refresh()
    return res


@app.post("/api/sessions/{event_id}/done")
def session_done(event_id: str):
    db.execute("UPDATE sessions SET done=1 WHERE event_id=?", (event_id,))
    log("Planner", "✔ Study session marked done — readiness updated.", "success")
    activity_log.refresh()
    return {"ok": True}


class DueIn(BaseModel):
    due: str  # "YYYY-MM-DDTHH:MM" local time


@app.post("/api/items/{item_id}/due")
async def set_due(item_id: str, body: DueIn):
    local = datetime.fromisoformat(body.due).replace(tzinfo=ZoneInfo(TIMEZONE))
    iso = local.astimezone(ZoneInfo("UTC")).isoformat()
    db.kv_set(f"due_override:{item_id}", iso)
    db.execute("UPDATE items SET due=? WHERE id=?", (iso, item_id))
    log("Coordinator", "Student confirmed a missing due date. Asking Planner to schedule.")
    res = await run(planner_agent.replan, item_id)
    activity_log.refresh()
    return res


# ---------- chat (ADK agent) ----------
class ChatIn(BaseModel):
    message: str
    session_id: str = "default"


@app.post("/api/chat")
async def chat(body: ChatIn):
    log("Coordinator", f"💬 Student: “{body.message}”")
    return {"reply": await chat_agent.chat(body.message, body.session_id)}


# ---------- WebSockets ----------
@app.websocket("/ws/activity")
async def ws_activity(ws: WebSocket):
    await ws.accept()
    activity_log.add_client(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        activity_log.remove_client(ws)


@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await voice_agent.voice_session(ws)
