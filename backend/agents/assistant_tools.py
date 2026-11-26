"""Tools the student-facing agent can call (shared by text chat and voice).
Each function has a clear docstring — Gemini reads it to decide when to call the tool."""
import difflib
from datetime import datetime
from zoneinfo import ZoneInfo

import db
from activity_log import log, push
from agents import planner_agent as planner
from config import TIMEZONE
from tools import calendar_tools as cal
from tools import study_tools as st

TZ = ZoneInfo(TIMEZONE)


def _find_item(name: str, prefer_kind: str = None):
    """Fuzzy-match a deadline by title or course name. prefer_kind='quiz' favours quizzes
    (so 'quiz me on DAA' picks the DAA quiz, not a DAA assignment)."""
    items = [i for i in st.upcoming_items(30) if i["due"]] or st.upcoming_items(30)
    if not items:
        return None
    name = (name or "").lower()
    scored = []
    for i in items:
        label = f"{i['course_name']} {i['title']}".lower()
        score = difflib.SequenceMatcher(None, name, label).ratio()
        score += 0.5 if name and name in label else 0
        score += 0.6 if i["course_name"].lower() in name or name in i["course_name"].lower() else 0
        score += 0.4 if prefer_kind and i["kind"] == prefer_kind else 0
        score -= 0.1 * min((i.get("days_left") or 0), 10) / 10  # sooner = slightly better
        scored.append((score, i))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _fmt(iso):
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%a %d %b %I:%M %p") if iso else "no date"


def get_upcoming_deadlines(days: int = 7) -> dict:
    """List the student's assignments and quizzes due in the next `days` days, most urgent first."""
    items = st.upcoming_items(days)
    return {"deadlines": [{"course": i["course_name"], "title": i["title"], "type": i["kind"],
                           "due": _fmt(i["due"]), "readiness_percent": i["readiness"]["score"]}
                          for i in items]}


def get_daily_brief() -> dict:
    """Get today's brief: what's due, what changed, what to study today."""
    return st.daily_brief()


def explain_lecture(topic: str, in_urdu: bool = False) -> dict:
    """Explain a lecture or topic simply, using the student's analyzed lecture slides.
    topic: lecture title, course name, or concept. in_urdu: true to answer in simple Urdu."""
    analyses = [db.cache_get(f"analysis:{r['file_id']}") for r in db.query("SELECT file_id FROM materials")]
    analyses = [a for a in analyses if a]
    if not analyses:
        return {"error": "No lectures analyzed yet."}
    t = topic.lower()

    def score(a):
        text = (a["title"] + " " + " ".join(c["name"] for c in a["key_concepts"])).lower()
        return difflib.SequenceMatcher(None, t, text).ratio() + (1 if t in text else 0)

    best = max(analyses, key=score)
    out = {"lecture": best["title"], "summary": best["summary"],
           "key_concepts": best["key_concepts"][:5], "exam_points": best["likely_exam_points"][:5]}
    if in_urdu:
        out["urdu_summary"] = st.explain_in_urdu(best["summary"])
    push({"type": "navigate", "to": f"/lecture/{best['file_id']}"})
    return out


def start_quiz(assessment_or_course: str) -> dict:
    """Start a practice quiz for a quiz/assignment or course. Returns the questions so you can
    ask them one by one. Also opens the quiz on screen."""
    item = _find_item(assessment_or_course, prefer_kind="quiz")
    if not item:
        return {"error": "No upcoming assessments found."}
    pack = st.build_prep_pack(item["id"])
    push({"type": "navigate", "to": f"/prep/{item['id']}?quiz=1"})
    log("Voice", f"Starting practice quiz for '{item['title']}'.")
    return {"assessment": item["title"], "questions": pack["quiz"]["questions"][:5]}


def get_readiness(assessment_or_course: str) -> dict:
    """How ready the student is (0-100%) for a quiz/assignment, from study sessions done and
    practice quiz scores."""
    item = _find_item(assessment_or_course, prefer_kind="quiz")
    if not item:
        return {"error": "No upcoming assessments found."}
    return {"assessment": item["title"], "course": item["course_name"], "due": _fmt(item["due"]),
            **st.readiness(item["id"])}


def list_study_sessions() -> dict:
    """List upcoming StudyPilot study sessions in Google Calendar with their event_id and time."""
    rows = db.query("SELECT event_id, title, start, end, done FROM sessions WHERE end>? "
                    "ORDER BY start", (datetime.now(TZ).isoformat(),))
    return {"now": datetime.now(TZ).strftime("%A %Y-%m-%d %H:%M"),
            "sessions": [{"event_id": r["event_id"], "title": r["title"], "start": _fmt(r["start"]),
                          "start_iso": r["start"]} for r in rows]}


def move_study_session(event_id: str, new_start_iso: str) -> dict:
    """Move one StudyPilot study session to a new start time.
    event_id: from list_study_sessions. new_start_iso: local time like 2026-11-27T19:00."""
    new_start = datetime.fromisoformat(new_start_iso)
    if new_start.tzinfo is None:
        new_start = new_start.replace(tzinfo=TZ)
    cal.move_study_event(event_id, new_start)
    log("Planner", f"Moved a study session to {_fmt(new_start.isoformat())} (student's request).",
        "success")
    push({"type": "refresh"})
    return {"ok": True, "new_start": _fmt(new_start.isoformat())}


def replan_assessment(assessment_or_course: str) -> dict:
    """Rebuild the Calendar study plan for one quiz/assignment."""
    item = _find_item(assessment_or_course)
    if not item:
        return {"error": "Not found"}
    res = planner.replan(item["id"], reason="student asked")
    push({"type": "refresh"})
    return res


def start_panic_mode(assessment_or_course: str, minutes_available: int = 120) -> dict:
    """Emergency mode when a quiz is very soon: makes a 20-minute cram sheet + 5 rapid questions."""
    item = _find_item(assessment_or_course, prefer_kind="quiz")
    if not item:
        return {"error": "No upcoming assessments found."}
    sheet = st.panic_mode(item["id"], minutes_available)
    push({"type": "navigate", "to": f"/panic/{item['id']}"})
    return {"headline": sheet["headline"], "top_topics": sheet["top_topics"]}


ALL_TOOLS = [get_upcoming_deadlines, get_daily_brief, explain_lecture, start_quiz, get_readiness,
             list_study_sessions, move_study_session, replan_assessment, start_panic_mode]
TOOLS_BY_NAME = {f.__name__: f for f in ALL_TOOLS}

SYSTEM_INSTRUCTION = (
    "You are StudyPilot, a friendly study coach for a university student in Pakistan. "
    "Answer briefly (1-3 sentences unless explaining). Reply in the language the student uses: "
    "English, Urdu, or Roman Urdu. Use your tools to get real data — never invent deadlines. "
    "When quizzing, ask one question at a time and wait for the answer. "
    "Never write or submit assignments for the student; explain and quiz instead. "
    "To move a session, first call list_study_sessions to get the event_id and today's date.")
