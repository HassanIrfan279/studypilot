"""Onboarding interview: Gemini gets to know the student, one question at a time, and builds a
profile the Planner and the Coordinator use (study window, class timetable, commitments,
goals, strictness). The class timetable can be uploaded as a photo and is read by Gemini."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel

import db
import gemini
import google_clients as g
from activity_log import log
from config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class Block(BaseModel):
    day: str          # Monday..Sunday
    start: str        # HH:MM 24h
    end: str          # HH:MM 24h
    label: str        # e.g. "COAL lecture", "Gym", "Part-time job"
    kind: str         # "class" | "commitment"


class Profile(BaseModel):
    name: str
    goals: str
    target_gpa: str
    hardest_courses: list[str]
    study_hours_per_day: float
    best_study_time: str      # e.g. "late night", "early morning"
    sleep_time: str           # HH:MM
    wake_time: str            # HH:MM
    weekly_blocks: list[Block]
    distractions: str
    language: str             # English / Urdu / Roman Urdu
    strictness: str           # "gentle" | "firm" | "very strict"
    summary: str              # 2-3 sentence portrait of the student for the agents


class Turn(BaseModel):
    done: bool
    message: str              # the next question (or the closing message)
    profile: Profile | None


class Timetable(BaseModel):
    blocks: list[Block]


def _context():
    courses = [r["name"] for r in db.query("SELECT name FROM courses")]
    name = db.kv_get("student_name") or ""
    if not name:
        try:
            name = g.oauth2().userinfo().get().execute().get("given_name", "")
            db.kv_set("student_name", name)
        except Exception:
            name = ""
    return name, courses


SYSTEM = """You are StudyPilot's tutor interviewing a new university student (FAST, Pakistan)
so you can plan their studies. Be warm, sharp and personal; use their name and their real
course names. Ask ONE short question at a time (max 2 sentences), react briefly to their last
answer, and adapt follow-ups to what they say.
Cover, in a natural order: goals (target GPA, what they want from this semester), hardest and
easiest courses, their weekly class timetable (days + times; tell them they can upload a photo
of it), how many hours a day they can really study, when they study best, sleep and wake time,
commute / part-time job / sports / family duties (with days and times), main distractions,
preferred language (English, Urdu or Roman Urdu), and how strict they want you to be.
After about 8-10 questions, or once you have enough, set done=true, write a short closing
message, and fill the full profile. Put every class and recurring commitment in weekly_blocks
with exact days and 24h times. Never invent facts: use "" or sensible defaults when unknown."""


def next_turn(messages: list[dict]) -> dict:
    """messages: [{"role": "agent"|"student", "text": "..."}]"""
    name, courses = _context()
    transcript = "\n".join(f"{'TUTOR' if m['role'] == 'agent' else 'STUDENT'}: {m['text']}"
                           for m in messages) or "(interview not started)"
    turn = gemini.generate_json(
        f"Student's first name: {name or 'unknown'}. Their courses this semester: "
        f"{', '.join(courses) or 'unknown'}. Today: {datetime.now(TZ):%A %d %B %Y}.\n\n"
        f"INTERVIEW SO FAR:\n{transcript}\n\nWrite your next turn.",
        Turn, system=SYSTEM)
    return turn


def read_timetable(image: bytes, mime: str) -> list[dict]:
    """Gemini reads a photo/screenshot of the class timetable."""
    out = gemini.generate_json(
        "This is a student's weekly class timetable (photo or screenshot). Extract every class "
        "as a block with day (Monday..Sunday), start and end in 24h HH:MM, a short label "
        "(course + room if shown), kind='class'. Ignore empty slots.",
        Timetable, parts=[gemini.file_part(image, mime)])
    log("Tutor", f"Read your timetable photo: {len(out['blocks'])} classes found.", "success")
    return out["blocks"]


def save_profile(profile: dict, add_to_calendar: bool = True) -> dict:
    db.kv_set("profile", profile)
    log("Coordinator", f"🧑‍🎓 Student profile saved: {profile.get('summary', '')[:160]}", "success")
    added = 0
    if add_to_calendar:
        added = _timetable_to_calendar(profile.get("weekly_blocks", []))
    return {"ok": True, "calendar_events": added}


def _timetable_to_calendar(blocks):
    """Weekly recurring events (tagged as StudyPilot timetable) so the Planner works around them."""
    svc = g.calendar()
    # remove an older timetable first
    old = svc.events().list(calendarId="primary", privateExtendedProperty=["studypilot=true", "kind=timetable"],
                            maxResults=250).execute().get("items", [])
    for ev in old:
        svc.events().delete(calendarId="primary", eventId=ev["id"]).execute()
    today = datetime.now(TZ).date()
    n = 0
    for b in blocks:
        if b["day"] not in DAYS:
            continue
        try:
            sh, sm = map(int, b["start"].split(":")[:2])
            eh, em = map(int, b["end"].split(":")[:2])
        except ValueError:
            continue
        delta = (DAYS.index(b["day"]) - today.weekday()) % 7
        day = today + timedelta(days=delta)
        start = datetime(day.year, day.month, day.day, sh, sm, tzinfo=TZ)
        end = datetime(day.year, day.month, day.day, eh, em, tzinfo=TZ)
        if end <= start:
            continue
        body = {"summary": f"{'🏫' if b.get('kind') == 'class' else '📌'} {b['label']}",
                "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
                "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
                "recurrence": ["RRULE:FREQ=WEEKLY;COUNT=16"],
                "colorId": "8",
                "reminders": {"useDefault": False},
                "extendedProperties": {"private": {"studypilot": "true", "kind": "timetable"}}}
        svc.events().insert(calendarId="primary", body=body).execute()
        n += 1
    log("Planner", f"📅 Added {n} weekly class/commitment blocks to Google Calendar — study "
                   "sessions will be planned around them.", "success")
    return n


def get_profile():
    return db.kv_get("profile") or {}
