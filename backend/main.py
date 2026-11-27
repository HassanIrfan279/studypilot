"""StudyPilot backend: FastAPI routes + WebSockets. Run with:  uvicorn main:app --reload --port 8000"""
import asyncio
import time
import os
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

import activity_log
import auth
import mcp_server
import db
import scheduler
from activity_log import log
import preflight
import runs
from agents import career_agent, chat_agent, coach, cv_builder, coordinator, interview, planner_agent, voice_agent, watcher
from tools import audit_tools as audit
from tools import notify as tg  # WhatsApp (Twilio) + Telegram
from config import FRONTEND_URL, TIMEZONE
from google_clients import NotLoggedIn
from tools import calendar_tools as cal
from tools import study_tools as st
from tools import notes_tools as notes


@asynccontextmanager
async def lifespan(app):
    activity_log.set_loop(asyncio.get_running_loop())
    from config import BACKGROUND_AGENT
    task = asyncio.create_task(scheduler.loop()) if BACKGROUND_AGENT else None
    if not BACKGROUND_AGENT:
        print("[StudyPilot] BACKGROUND_AGENT=false: web app only, no background agents in this copy.")
    async with mcp_server.mcp.session_manager.run():  # the agents' MCP tool server, at /mcp/
        yield
    if task:
        task.cancel()
    # Background Google/Gemini calls run in worker threads; don't wait for them on Ctrl-C
    os._exit(0)


app = FastAPI(title="StudyPilot", lifespan=lifespan)
app.mount("/mcp", mcp_server.asgi_app)  # MCP server (Streamable HTTP) the Coordinator agent calls its tools on
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
    try:
        missing = await run(auth.handle_callback, str(request.url), state)
    except auth.NotOwner:
        log("Coordinator", "🔒 Someone else tried to sign in. Blocked: this StudyPilot belongs to its owner.", "warn")
        return RedirectResponse(f"{FRONTEND_URL}/?login_error=not_owner")
    if missing:
        log("Coordinator", "Sign-in is missing permissions (Classroom/Drive/Calendar boxes not "
                           "ticked). Asking the student to sign in again.", "error")
        return RedirectResponse(f"{FRONTEND_URL}/?missing_scopes=1")
    log("Coordinator", "✅ Signed in with Google. Starting first sync…", "success")
    asyncio.create_task(run(scheduler.sync_once, True))
    return RedirectResponse(FRONTEND_URL)


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


# ---------- study notes (editable, AI-editable, PDF, mirrored to Drive) ----------
class NotesIn(BaseModel):
    md: str = ""
    instruction: str = ""


def _notes_out(n):
    if n:
        n = {k: v for k, v in n.items() if k != "history"}
    return n


@app.get("/api/notes/{assessment_id}")
async def get_notes(assessment_id: str, generate: bool = False, refresh: bool = False):
    n = notes.get_notes(assessment_id)
    if (generate and not n) or refresh:
        try:
            n = await run(notes.generate_notes, assessment_id, refresh)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    item = st.get_item(assessment_id)
    return {"notes": _notes_out(n), "item": item,
            "course_name": item and st.course_name(item["course_id"]),
            "color": item and cal.COLOR_HEX[cal.course_color(item["course_id"])]}


@app.put("/api/notes/{assessment_id}")
async def save_notes(assessment_id: str, body: NotesIn):
    return _notes_out(await run(notes.save_manual, assessment_id, body.md))


@app.post("/api/notes/{assessment_id}/ai-edit")
async def ai_edit_notes(assessment_id: str, body: NotesIn):
    try:
        return _notes_out(await run(notes.edit_notes, assessment_id, body.instruction))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/notes/{assessment_id}/undo")
async def undo_notes(assessment_id: str):
    return _notes_out(await run(notes.undo, assessment_id))


@app.get("/api/notes/{assessment_id}/pdf")
async def notes_pdf(assessment_id: str):
    try:
        data = await run(notes.notes_pdf, assessment_id)
    except Exception as e:
        return JSONResponse({"error": f"Drive export failed: {e}"}, status_code=502)
    if not data:
        return JSONResponse({"error": "No notes yet"}, status_code=404)
    item = st.get_item(assessment_id) or {"title": "notes"}
    name = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in item["title"]).strip()
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name} - StudyPilot notes.pdf"'})


@app.post("/api/drive/organize")
async def organize_drive():
    await run(notes.organize_drive, [i for i in st.upcoming_items(14) if i["due"]])
    return {"ok": True, "folder": db.kv_get("folder:root:StudyPilot")}


class ScoreIn(BaseModel):
    score: float  # 0..1
    wrong: list[str] = []  # questions the student got wrong


@app.post("/api/quiz/{assessment_id}/result")
async def quiz_result(assessment_id: str, body: ScoreIn):
    st.save_quiz_result(assessment_id, body.score, body.wrong)
    activity_log.refresh()
    asyncio.create_task(run(st.prepare_next_quiz, assessment_id))  # every attempt -> new questions next time
    if body.wrong:  # wrong topics come back after 1, 3 and 7 days
        asyncio.create_task(run(coach.schedule_reviews, assessment_id, body.wrong))
    if body.score < 0.6:  # weak result -> the agent reacts on its own
        asyncio.create_task(run(watcher.on_quiz_result, assessment_id, body.score, body.wrong))
    return st.readiness(assessment_id)


@app.get("/api/preflight")
async def preflight_check():
    """Tests every service the demo needs (read-only) — run this before going on stage."""
    return await run(preflight.run_all)


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
    return await run(st.take_next_quiz, assessment_id, n)


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
            msg = await ws.receive_text()
            if msg == "active":
                activity_log.mark_active(ws)
    except WebSocketDisconnect:
        pass
    finally:
        activity_log.remove_client(ws)


@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await voice_agent.voice_session(ws)


# ---------- internships (career agent) ----------
class CvIn(BaseModel):
    pdf_base64: str


class TextIn(BaseModel):
    text: str = ""
    url: str = ""


class AnswerIn(BaseModel):
    question: str
    answer: str


class AppEditIn(BaseModel):
    cover_letter: str | None = None
    subject: str | None = None
    instruction: str | None = None


def _bad(e):
    return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/internships")
async def internships():
    return {"profile": career_agent.profile(), "items": career_agent.all_items(),
            "answers": db.kv_get("career_answers") or {}, "can_draft": career_agent.has_compose(),
            "last_run": db.kv_get("career_last_run"),
            "web_search": (db.kv_get("career_web_off_until") or 0) < time.time()}


@app.post("/api/internships/cv")
async def upload_cv(body: CvIn):
    import base64
    try:
        data = base64.b64decode(body.pdf_base64.split(",")[-1])
        if len(data) > 8_000_000:
            return _bad("CV is too large (max 8 MB).")
        return await run(career_agent.save_cv, data)
    except ValueError as e:
        return _bad(e)


@app.patch("/api/internships/profile")
async def patch_career_profile(body: dict):
    return career_agent.update_profile(body)


@app.post("/api/internships/answer")
async def answer_career_question(body: AnswerIn):
    return career_agent.answer_gap(body.question, body.answer)


@app.post("/api/internships/run")
async def run_internships():
    asyncio.create_task(run(career_agent.run, True))
    return {"started": True}


@app.post("/api/internships/add")
async def add_internship(body: TextIn):
    try:
        return await run(career_agent.add_manual, body.text, body.url)
    except ValueError as e:
        return _bad(e)


@app.post("/api/internships/{iid}/write")
async def write_internship(iid: str, body: AppEditIn):
    return await run(career_agent.write_application, iid, body.instruction or "")


@app.patch("/api/internships/{iid}/app")
async def edit_internship_app(iid: str, body: AppEditIn):
    return career_agent.edit_application(iid, body.cover_letter, body.subject)


@app.post("/api/internships/{iid}/approve")
async def approve_internship(iid: str):
    try:
        return await run(career_agent.approve, iid)
    except ValueError as e:
        return _bad(e)


@app.post("/api/internships/{iid}/follow-up")
async def approve_follow_up(iid: str):
    try:
        return await run(career_agent.approve_follow_up, iid)
    except ValueError as e:
        return _bad(e)


@app.post("/api/internships/{iid}/status/{status}")
async def internship_status(iid: str, status: str):
    try:
        return career_agent.set_status(iid, status)
    except ValueError as e:
        return _bad(e)


class CvTurnIn(BaseModel):
    messages: list[dict] = []
    finish: bool = False


class InstructionIn(BaseModel):
    instruction: str


@app.post("/api/cv/interview")
async def cv_interview(body: CvTurnIn):
    return await run(cv_builder.next_turn, body.messages, body.finish)


@app.get("/api/cv")
async def cv_draft():
    d = cv_builder.get_draft()
    return {"draft": d, "has_pdf": career_agent.CV_PATH.exists(),
            "pdf_version": int(career_agent.CV_PATH.stat().st_mtime) if career_agent.CV_PATH.exists() else 0}


@app.get("/api/cv/pdf")
async def cv_pdf():
    if not career_agent.CV_PATH.exists():
        return JSONResponse({"error": "No CV yet"}, status_code=404)
    prof = career_agent.profile() or {}
    name = "".join(ch if ch.isalnum() else "_" for ch in (prof.get("name") or "My")).strip("_") + "_CV.pdf"
    return FileResponse(career_agent.CV_PATH, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{name}"'})


@app.post("/api/cv/edit")
async def cv_edit(body: InstructionIn):
    try:
        return await run(cv_builder.ai_edit, body.instruction)
    except ValueError as e:
        return _bad(e)


@app.post("/api/cv/sync")
async def cv_sync():
    try:
        return await run(cv_builder.sync_from_doc)
    except ValueError as e:
        return _bad(e)


# ---------- coach: habits, goals, reviews, tradeoffs, nightly review ----------
class GoalIn(BaseModel):
    grade: str = ""


class DecideIn(BaseModel):
    feedback: str = ""


class ReviewScoreIn(BaseModel):
    score: float


@app.get("/api/coach")
async def coach_state():
    def gather():
        return {"habits": coach.habit_stats(), "goals": coach.goal_status(), "reviews": coach.reviews(),
                "proposals": coach.pending_proposals(), "last_review": db.kv_get("last_review"),
                "review_hour": coach.REVIEW_HOUR}
    return await run(gather)


@app.put("/api/goals/{course_id}")
async def put_goal(course_id: str, body: GoalIn):
    return await run(coach.set_goal, course_id, body.grade)


@app.post("/api/review/run")
async def run_review_now():
    asyncio.create_task(run(coach.nightly_review, "manual"))
    return {"started": True}


@app.post("/api/workload/check")
async def workload_check():
    return await run(coach.propose_tradeoff)


@app.post("/api/proposals/{pid}/{action}")
async def decide_proposal(pid: int, action: str, body: DecideIn):
    try:
        return await run(coach.decide, pid, action, body.feedback)
    except ValueError as e:
        return _bad(e)


@app.get("/api/reviews/{rid}/quiz")
async def review_quiz(rid: int):
    out = await run(coach.review_quiz, rid)
    return out or JSONResponse({"error": "Unknown review"}, status_code=404)


@app.post("/api/reviews/{rid}/result")
async def review_result(rid: int, body: ReviewScoreIn):
    return await run(coach.review_result, rid, body.score)


@app.post("/api/internships/track")
async def track_internships():
    await run(career_agent.track)
    return {"ok": True}


# ---------- deployed: serve the built React app from the same server ----------
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST in f.parents:
            return FileResponse(f)
        if path.startswith(("api/", "auth/", "ws/")):
            return JSONResponse({"error": "Not found"}, status_code=404)
        return FileResponse(DIST / "index.html")
