"""StudyPilot backend: FastAPI routes + WebSockets. Run with:  uvicorn main:app --reload --port 8000"""
import asyncio
import os
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
import runs
from agents import chat_agent, coordinator, interview, planner_agent, voice_agent, watcher
from tools import audit_tools as audit
from tools import notify as tg  # WhatsApp (Twilio) + Telegram
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
    # Background Google/Gemini calls run in worker threads; don't wait for them on Ctrl-C
    os._exit(0)


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
    missing = await run(auth.handle_callback, str(request.url), state)
    if missing:
        log("Coordinator", "Sign-in is missing permissions (Classroom/Drive/Calendar boxes not "
                           "ticked). Asking the student to sign in again.", "error")
        auth.logout()
        return RedirectResponse(f"{FRONTEND_URL}/?missing_scopes=1")
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
    granted = set((db.kv_get("token") or {}).get("scopes") or [])
    from config import SCOPES
    needs_upgrade = bool(creds) and any(s not in granted for s in SCOPES
                                        if "gmail" in s or "drive.file" in s)
    return {"logged_in": bool(creds), "last_sync": db.kv_get("last_sync"),
            "needs_upgrade": needs_upgrade, "profile_done": bool(db.kv_get("profile"))}


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
        i["flags"] = db.kv_get(f"flags:{i['id']}") or []
        i["sessions"] = db.one("SELECT COUNT(*) n FROM sessions WHERE assessment_id=? AND done=0 "
                               "AND end>?", (i["id"], datetime.now(ZoneInfo(TIMEZONE)).isoformat()))["n"]
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
        pack["color"] = cal.COLOR_HEX[cal.course_color(pack["assessment"]["course_id"])]
    return pack


class ScoreIn(BaseModel):
    score: float  # 0..1
    wrong: list[str] = []  # questions the student got wrong


@app.post("/api/quiz/{assessment_id}/result")
async def quiz_result(assessment_id: str, body: ScoreIn):
    st.save_quiz_result(assessment_id, body.score, body.wrong)
    activity_log.refresh()
    if body.score < 0.6:  # weak result -> the agent reacts on its own
        asyncio.create_task(run(watcher.on_quiz_result, assessment_id, body.score, body.wrong))
    return st.readiness(assessment_id)


@app.get("/api/runs")
def agent_runs():
    return runs.recent(15)


@app.get("/api/notify")
async def telegram_status():
    return await run(tg.status)


@app.post("/api/notify/test")
async def telegram_test():
    ok = await run(tg.send, "📘 <b>StudyPilot</b> is connected. I'll message you here when "
                            "your plan changes.")
    return {"sent": ok}


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
                            "color": colors.get(p["course_id"], "#3f51b5"),
                            "priority": p["priority"], "due": p["due"]} for p in priorities]}


@app.post("/api/warmup")
async def warmup():
    """Analyze lectures, book the plan and build prep packs (use before a demo)."""
    asyncio.create_task(run(coordinator.warm_up))
    return {"started": True}


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


@app.get("/api/quiz/{assessment_id}/new")
async def new_quiz(assessment_id: str, n: int = 8):
    """Retake: a brand-new set of questions aimed at previous mistakes."""
    log("Tutor", "Writing a brand-new quiz aimed at your previous mistakes…")
    return await run(st.fresh_questions, assessment_id, n, "retake")


@app.post("/api/sessions/{event_id}/check")
async def session_check(event_id: str):
    """Strict teacher: before a session counts as done, prove it with 3 fresh questions."""
    s = db.one("SELECT * FROM sessions WHERE event_id=?", (event_id,))
    if not s:
        return JSONResponse({"error": "unknown session"}, status_code=404)
    log("Tutor", "Session marked done — not so fast. Generating a 3-question check first.")
    return await run(st.fresh_questions, s["assessment_id"], 3, "check")


class CheckIn(BaseModel):
    score: float
    wrong: list[str] = []


@app.post("/api/sessions/{event_id}/verify")
async def session_verify(event_id: str, body: CheckIn):
    s = db.one("SELECT * FROM sessions WHERE event_id=?", (event_id,))
    if not s:
        return JSONResponse({"error": "unknown session"}, status_code=404)
    st.save_quiz_result(s["assessment_id"], body.score, body.wrong)
    if body.score >= 0.66:
        db.execute("UPDATE sessions SET done=1 WHERE event_id=?", (event_id,))
        log("Tutor", f"✔ Check passed ({round(body.score * 3)}/3). Session counts as done.", "success")
        msg = "Good. That session counts. Readiness updated."
        passed = True
    else:
        log("Tutor", f"✘ Check failed ({round(body.score * 3)}/3). Session NOT counted.", "warn")
        msg = ("Not convinced. You didn't really cover this yet, so the session doesn't count. "
               "Review the prep pack and try the check again.")
        passed = False
        asyncio.create_task(run(watcher.on_quiz_result, s["assessment_id"], body.score, body.wrong))
    activity_log.refresh()
    return {"passed": passed, "message": msg, "readiness": st.readiness(s["assessment_id"])}


@app.post("/api/sessions/{event_id}/done")
def session_done(event_id: str):
    db.execute("UPDATE sessions SET done=1 WHERE event_id=?", (event_id,))
    log("Planner", "✔ Study session marked done — readiness updated.", "success")
    activity_log.refresh()
    return {"ok": True}


@app.post("/api/items/{item_id}/audit")
async def audit_now(item_id: str):
    item = st.get_item(item_id)
    issues = await run(audit.audit_item, item)
    activity_log.refresh()
    return {"flags": issues}


@app.post("/api/items/{item_id}/flags/clear")
def flags_clear(item_id: str):
    audit.clear_flag(item_id)
    log("Coordinator", "Student reviewed the flagged deadline and confirmed it's correct.")
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


# ---------- onboarding interview + profile ----------
class InterviewIn(BaseModel):
    messages: list[dict] = []


@app.post("/api/interview")
async def interview_turn(body: InterviewIn):
    return await run(interview.next_turn, body.messages)


class ImageIn(BaseModel):
    data_base64: str
    mime: str = "image/jpeg"


@app.post("/api/interview/timetable")
async def interview_timetable(body: ImageIn):
    import base64
    blocks = await run(interview.read_timetable, base64.b64decode(body.data_base64), body.mime)
    return {"blocks": blocks}


class ProfileIn(BaseModel):
    profile: dict
    add_to_calendar: bool = True


@app.post("/api/profile")
async def save_profile(body: ProfileIn):
    res = await run(interview.save_profile, body.profile, body.add_to_calendar)
    activity_log.refresh()
    from agents import brain
    p = body.profile
    asyncio.create_task(run(
        brain.think_and_act, "profile", f"Re-planning around {p.get('name') or 'you'}",
        "The student just finished the onboarding interview. Their profile: " + str(p)[:2500] +
        "\n\nTheir weekly classes/commitments are now in Google Calendar. Review all upcoming "
        "deadlines (list_upcoming): give their hardest courses more preparation, re-plan any "
        "deadline whose sessions now clash or are too few, verify, then send one short "
        "personalised message about the plan (in their preferred language)."))
    return res


@app.get("/api/profile")
def get_profile():
    return interview.get_profile()


# ---------- in-app calendar (two-way with Google Calendar) ----------
@app.get("/api/calendar")
async def calendar_events(start: str, end: str):
    return await run(cal.events_for_ui, start, end)


class EventIn(BaseModel):
    title: str = ""
    start: str
    end: str


@app.post("/api/calendar/events")
async def calendar_add(body: EventIn):
    ev = await run(cal.add_student_event, body.title, body.start, body.end)
    log("Planner", f"📅 You added '{body.title}' to your calendar. Checking it against your study plan…")
    asyncio.create_task(run(watcher.check_clashes))  # agent reacts if it clashes with a session
    return ev


@app.patch("/api/calendar/events/{event_id}")
async def calendar_move(event_id: str, body: EventIn):
    res = await run(cal.update_event_from_ui, event_id, body.start, body.end, body.title)
    asyncio.create_task(run(watcher.check_clashes))
    activity_log.refresh()
    return res


@app.delete("/api/calendar/events/{event_id}")
async def calendar_delete(event_id: str):
    res = await run(cal.delete_event_from_ui, event_id)
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
