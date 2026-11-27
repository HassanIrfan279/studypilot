"""The Coordinator's brain: Gemini decides what to do.

Every trigger (teacher change, calendar clash, missed session, weak quiz…) becomes an
"agent run". Gemini gets the goal + a toolbox, reasons, calls tools one by one, reads the
results, verifies its own work in Google Calendar, and tells the student what it did.
Each thought and action is streamed to the UI. If Gemini fails, the caller falls back to
the fixed rule-based pipeline, so the student is never left without a plan.
"""
import time
import json
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from google.genai import types

import db
import gemini
import runs
from activity_log import announce, log, refresh
from agents import planner_agent as planner
from config import TIMEZONE
from tools import calendar_tools as cal
from tools import study_tools as st
from tools import notify as tg  # WhatsApp (Twilio) + Telegram

TZ = ZoneInfo(TIMEZONE)
MAX_STEPS = 14
RUN_BUDGET = 90  # seconds: a single agent run can never block the demo for long
_ctx = threading.local()  # which run the tools are reporting to


def _fmt(iso):
    if not iso:
        return "no date"
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%a %d %b %I:%M %p")


def _say(kind, text):
    runs.step(getattr(_ctx, "run_id", None), kind, text)


# =====================  TOOLS GEMINI CAN USE  =====================
def get_deadline(item_id: str) -> dict:
    """Full details of one deadline: course, type, due date, lectures it covers, readiness,
    booked study sessions, and any flags raised about it."""
    it = st.get_item(item_id)
    if not it:
        return {"error": "unknown item_id"}
    lectures = []
    for fid in st.lectures_for_assessment(item_id):
        m = db.one("SELECT title FROM materials WHERE file_id=?", (fid,))
        a = db.cache_get(f"analysis:{fid}")
        lectures.append({"file_id": fid, "title": m["title"] if m else fid, "analyzed": bool(a),
                         "difficulty": a.get("difficulty") if a else None,
                         "study_hours": a.get("estimated_study_hours") if a else None})
    sessions = db.query("SELECT event_id, start, end, done FROM sessions WHERE assessment_id=? "
                        "ORDER BY start", (item_id,))
    return {"item_id": item_id, "title": it["title"], "kind": it["kind"],
            "course": st.course_name(it["course_id"]), "due": _fmt(it["due"]),
            "active": bool(it["active"]), "source": it["source"], "evidence": it["description"],
            "lectures": lectures, "readiness": st.readiness(item_id),
            "sessions": [{"event_id": s["event_id"], "start": _fmt(s["start"]), "done": bool(s["done"])}
                         for s in sessions],
            "flags": db.kv_get(f"flags:{item_id}") or []}


def get_student_profile() -> dict:
    """What we know about the student from the onboarding interview: goals, target GPA,
    hardest courses, study hours per day, best study time, sleep, weekly commitments,
    language and how strict they want you to be. Use it to personalise decisions."""
    p = db.kv_get("profile") or {}
    return p or {"note": "No interview yet — use sensible defaults."}


def list_upcoming() -> dict:
    """All upcoming deadlines (next 14 days) with readiness and number of study sessions."""
    out = []
    for i in st.upcoming_items(14):
        n = db.one("SELECT COUNT(*) n FROM sessions WHERE assessment_id=?", (i["id"],))["n"]
        out.append({"item_id": i["id"], "title": i["title"], "course": i["course_name"],
                    "kind": i["kind"], "due": _fmt(i["due"]), "readiness": i["readiness"]["score"],
                    "sessions": n})
    return {"now": datetime.now(TZ).strftime("%A %d %b %H:%M"), "deadlines": out}


def analyze_lecture(file_id: str) -> dict:
    """Have the Tutor read a lecture file (PDF/PPTX/Slides) and return its summary, difficulty
    and estimated study hours. Cached: never reads the same file twice."""
    _say("act", "Tutor is reading the lecture with Gemini")
    a = st.analyze_lecture(file_id)
    return {"title": a["title"], "difficulty": a["difficulty"],
            "study_hours": a["estimated_study_hours"],
            "key_concepts": [c["name"] for c in a["key_concepts"]]}


def build_prep_pack(item_id: str) -> dict:
    """Build (or rebuild) the prep pack for a deadline: lecture summaries, exam points,
    a practice quiz and YouTube explainer videos."""
    _say("act", "Tutor is building the prep pack")
    pack = st.build_prep_pack(item_id, refresh=True)
    if not pack:
        return {"error": "unknown item"}
    return {"lectures": [l["title"] for l in pack["lectures"]],
            "quiz_questions": len(pack["quiz"]["questions"]),
            "videos": sum(len(v["videos"]) for v in pack["videos"])}


def plan_sessions(item_id: str) -> dict:
    """Book study sessions in Google Calendar before this deadline (replaces any future
    StudyPilot sessions for it). Avoids the student's existing events."""
    _say("act", "Planner is booking study time in Google Calendar")
    out = planner.replan(item_id, "agent decision")
    from agents import coach
    out["reviewer"] = coach.review_plan(item_id)
    return out


def clear_sessions(item_id: str) -> dict:
    """Remove all future StudyPilot study sessions for a deadline (e.g. it was cancelled)."""
    _say("act", "Planner is clearing study sessions")
    removed = 0
    for ev in cal.list_studypilot_events(item_id):
        cal.delete_study_event(ev["id"])
        removed += 1
    return {"removed": removed}


def add_extra_session(item_id: str, minutes: int, focus: str) -> dict:
    """Book ONE extra focused study session before the deadline, e.g. after a weak quiz score.
    focus: the exact topics to work on."""
    it = st.get_item(item_id)
    if not it or not it["due"]:
        return {"error": "deadline has no due date"}
    minutes = max(30, min(int(minutes), 120))
    due = datetime.fromisoformat(it["due"]).astimezone(TZ)
    from agents import coach  # the Reviewer agent must approve the slot (clashes, breaks, load)
    slot = coach.reviewed_slot(minutes, datetime.now(TZ) + timedelta(minutes=30), due - timedelta(hours=2), it)
    if not slot:
        return {"error": "no free time before the deadline that the Reviewer approves"}
    _say("act", f"Planner is booking an extra {minutes}-min session on {focus}")
    ev = cal.create_study_event(it, st.course_name(it["course_id"]), slot[0], slot[1], 0, 0, focus=focus)
    return {"event_id": ev["id"], "start": slot[0].strftime("%a %d %b %H:%M")}


def move_session(event_id: str, new_start_iso: str) -> dict:
    """Move one StudyPilot study session to a new start time (local time, e.g. 2026-11-28T20:00).
    Use find_free_slot first to pick a time that does not clash."""
    start = datetime.fromisoformat(new_start_iso)
    if start.tzinfo is None:
        start = start.replace(tzinfo=TZ)
    from agents import coach
    row = db.one("SELECT * FROM sessions WHERE event_id=?", (event_id,))
    if row:
        length = datetime.fromisoformat(row["end"]) - datetime.fromisoformat(row["start"])
        verdict = coach.reviewer_check(start, start + length, st.get_item(row["assessment_id"]), ignore_event=event_id)
        if not verdict["ok"]:
            return {"rejected_by_reviewer": verdict["reasons"],
                    "hint": "Pick a different time with find_free_slot (later in the day or another day)."}
    _say("act", f"Planner is moving a session to {start.strftime('%a %H:%M')}")
    cal.move_study_event(event_id, start)
    return {"ok": True, "new_start": start.strftime("%a %d %b %H:%M")}


def find_free_slot(minutes: int, after_iso: str, before_iso: str) -> dict:
    """Find the first free time of `minutes` in the student's study window between two local
    times (ISO, e.g. 2026-11-28T09:00). Respects every existing calendar event."""
    after = datetime.fromisoformat(after_iso)
    before = datetime.fromisoformat(before_iso)
    after = after if after.tzinfo else after.replace(tzinfo=TZ)
    before = before if before.tzinfo else before.replace(tzinfo=TZ)
    after = max(after, datetime.now(TZ) + timedelta(minutes=15))
    slot = cal.find_free_slot(int(minutes), after, before)
    if not slot:
        return {"found": False}
    return {"found": True, "start_iso": slot[0].strftime("%Y-%m-%dT%H:%M"),
            "end_iso": slot[1].strftime("%Y-%m-%dT%H:%M")}


def sessions_between(after_iso: str, before_iso: str) -> dict:
    """List StudyPilot study sessions booked between two local times, with which deadline each
    one is for and when that deadline is due. Use this to find a LESS urgent session you could
    move to make room for a more urgent deadline."""
    a = datetime.fromisoformat(after_iso)
    b = datetime.fromisoformat(before_iso)
    a = (a if a.tzinfo else a.replace(tzinfo=TZ)).isoformat()
    b = (b if b.tzinfo else b.replace(tzinfo=TZ)).isoformat()
    out = []
    for s in db.query("SELECT * FROM sessions WHERE done=0 AND start>=? AND start<? ORDER BY start", (a, b)):
        it = st.get_item(s["assessment_id"]) or {}
        out.append({"event_id": s["event_id"], "start": _fmt(s["start"]), "end": _fmt(s["end"]),
                    "for_item_id": s["assessment_id"], "for": it.get("title"),
                    "that_deadline_due": _fmt(it.get("due"))})
    return {"sessions": out}


def verify_calendar(item_id: str) -> dict:
    """Read Google Calendar back and confirm what is really booked for this deadline
    (study sessions + the deadline marker). Always call this after changing the plan."""
    _say("act", "Checking Google Calendar to verify the plan")
    events = cal.list_studypilot_events(item_id, future_only=False, include_deadlines=True)
    sessions = [e for e in events if cal._kind(e) != "deadline"
                and datetime.fromisoformat(e["end"]["dateTime"]) > datetime.now(timezone.utc)]
    marker = [e for e in events if cal._kind(e) == "deadline"]
    return {"future_sessions": [{"event_id": e["id"],
                                 "start": datetime.fromisoformat(e["start"]["dateTime"]).astimezone(TZ).strftime("%a %d %b %H:%M")}
                                for e in sessions],
            "deadline_marker": marker[0]["start"]["dateTime"] if marker else None}


def notify_student(message: str) -> dict:
    """Tell the student what changed and what you did: shown on screen, spoken aloud, and sent
    to their phone on Telegram. Call this ONCE at the end of a run. Max 2 short sentences."""
    announce(message)
    sent = tg.send(f"📘 <b>StudyPilot</b>\n{message}")
    _say("say", message + ("  (sent to your phone)" if sent else ""))
    return {"shown": True, "telegram": sent}


def ask_student(item_id: str, question: str) -> dict:
    """Ask the student a question when something is unclear (e.g. a missing or ambiguous date).
    Never guess dates."""
    qs = db.kv_get("questions") or []
    qs.append({"item_id": item_id, "question": question, "ts": datetime.now(TZ).isoformat()})
    db.kv_set("questions", qs[-20:])
    _say("ask", question)
    tg.send(f"❓ <b>StudyPilot needs you</b>\n{question}")
    return {"asked": True}


def flag_issue(item_id: str, issue: str) -> dict:
    """Mark something wrong or unusual about a deadline (contradictory dates, date in the past,
    weekend quiz, etc.) so the student reviews it."""
    flags = db.kv_get(f"flags:{item_id}") or []
    if issue not in flags:
        flags.append(issue)
    db.kv_set(f"flags:{item_id}", flags)
    _say("warn", f"Flagged: {issue}")
    return {"flagged": True}


def rewrite_study_notes(item_id: str, instruction: str) -> dict:
    """Rewrite the student's study notes for a deadline (e.g. re-teach the topics they got wrong
    more simply with new worked examples). Creates the notes first if they don't exist yet."""
    from tools import notes_tools as notes
    try:
        if not notes.get_notes(item_id):
            notes.generate_notes(item_id)
        n = notes.edit_notes(item_id, instruction, reason="Rewritten by the agent")
        return {"ok": True, "version": n["version"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


TOOLS = [get_deadline, list_upcoming, get_student_profile, analyze_lecture, build_prep_pack, plan_sessions,
         clear_sessions, add_extra_session, move_session, find_free_slot, sessions_between,
         verify_calendar,
         rewrite_study_notes, notify_student, ask_student, flag_issue]
TOOL_MAP = {f.__name__: f for f in TOOLS}

SYSTEM = """You are the Coordinator of StudyPilot, a strict but caring study agent for a
university student in Pakistan. You run autonomously: something just happened, and you must
decide what to do and DO it with your tools, end to end.

How you work:
- First think in one or two short sentences about what matters (write it as plain text).
- Personalise: check get_student_profile (hardest courses get more time; respect their
  commitments; match the strictness and language they asked for).
- Then act with tools. Look things up before deciding (get_deadline, list_upcoming).
- Make sure every upcoming deadline has a prep pack and study sessions before it.
- After any calendar change, ALWAYS call verify_calendar to confirm it really happened.
- Never guess a missing date: use ask_student. Flag anything contradictory with flag_issue.
- PRIORITIZE: if an urgent deadline (e.g. tomorrow) has no free time, call sessions_between
  for the time before it. If a session there belongs to a LATER deadline, move that session
  to a free slot after the urgent deadline (find_free_slot, then move_session), then book the
  urgent deadline's time (plan_sessions or add_extra_session). Explain the trade-off.
- If there is truly no time, book even 30-45 minutes and tell the student to use Panic mode.
  Never leave a deadline with zero preparation without saying so.
- Finish with exactly one notify_student call: what changed + what you did, max 2 sentences,
  direct and specific (course, item, new time). Then reply with a one-line summary.
- Be efficient: don't repeat tool calls you already made."""


def _decls():
    return [types.FunctionDeclaration.from_callable(client=gemini.client._api_client, callable=f)
            for f in TOOLS]


def _short(v, n=180):
    s = json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + "…"


def _human(name, args):
    a = ", ".join(f"{v}" for v in args.values()) if args else ""
    return f"{name.replace('_', ' ')}({a})"


_one_run_at_a_time = threading.Lock()


def think_and_act(trigger: str, title: str, situation: str) -> bool:
    """Run Gemini's reasoning loop for one trigger. Returns True on success.
    Runs are serialized: two runs planning at once would both pick the same free slot."""
    with _one_run_at_a_time:
        return _think_and_act(trigger, title, situation)


def _think_and_act(trigger: str, title: str, situation: str) -> bool:
    run_id = runs.start(trigger, title)
    _ctx.run_id = run_id
    now = datetime.now(TZ).strftime("%A %d %b %Y %H:%M")
    contents = [types.Content(role="user", parts=[types.Part(text=f"Now: {now}\n\nSITUATION:\n{situation}")])]
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM, temperature=0.2,
        tools=[types.Tool(function_declarations=_decls())],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    notified, summary, acted = False, "", False
    started = time.time()
    config.http_options = types.HttpOptions(timeout=25_000)
    try:
        for _ in range(MAX_STEPS):
            if time.time() - started > RUN_BUDGET:
                runs.step(run_id, "warn", "Took too long, so I'm wrapping up with what's done.")
                break
            resp = gemini._call(contents, config, budget=40)
            cand = resp.candidates[0].content if resp.candidates else None
            if not cand or not cand.parts:
                break
            contents.append(cand)
            calls = [p.function_call for p in cand.parts if p.function_call]
            for p in cand.parts:
                if p.text and p.text.strip() and not getattr(p, "thought", False):
                    (runs.step(run_id, "think", p.text.strip()) if calls else None)
                    summary = p.text.strip()
            if not calls:
                break
            replies = []
            for fc in calls:
                args = dict(fc.args or {})
                runs.step(run_id, "act", _human(fc.name, args))
                acted = True
                fn = TOOL_MAP.get(fc.name)
                try:
                    out = fn(**args) if fn else {"error": f"unknown tool {fc.name}"}
                except Exception as e:
                    out = {"error": str(e)}
                    runs.step(run_id, "warn", f"{fc.name} failed: {e}")
                else:
                    runs.step(run_id, "ok", _short(out))
                if fc.name == "notify_student":
                    notified = True
                replies.append(types.Part.from_function_response(name=fc.name, response={"result": out}))
            contents.append(types.Content(role="user", parts=replies))
        if not notified and acted:
            notify_student(summary[:300] if summary else f"I handled it: {title}.")
        runs.finish(run_id, "done", summary or "Done.")
        db.cache_delete("brief")
        refresh()
        return True
    except Exception as e:
        if acted:
            # Tools already changed the calendar: don't let the backup rules do it all a second time
            runs.step(run_id, "warn", f"Gemini stopped mid-run ({type(e).__name__}); keeping what's done.")
            if not notified:
                notify_student(f"I updated your plan for: {title}.")
            runs.finish(run_id, "done", summary or "Done (partly).")
            db.cache_delete("brief")
            refresh()
            return True
        log("Coordinator", f"Gemini brain failed ({type(e).__name__}) — using the backup "
                           "rule-based plan.", "warn")
        runs.step(run_id, "warn", f"Gemini unavailable: {e}. Switching to backup rules.")
        runs.finish(run_id, "fallback", "Handled by backup rules.")
        return False
    finally:
        _ctx.run_id = None
