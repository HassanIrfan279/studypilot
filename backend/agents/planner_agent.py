"""Planner agent: decides how much to study, finds free time, and books Calendar sessions."""
import math
from datetime import datetime, timedelta, timezone

import db
from activity_log import log
from tools import calendar_tools as cal
from tools import study_tools as st

PREFERRED_START_HOUR = 17  # try to put sessions in the evening, after class


def estimate_hours(item):
    """Study hours = sum of linked lecture estimates (cached analyses), with sensible bounds."""
    hours = 0.0
    for fid in st.lectures_for_assessment(item["id"]):
        a = db.cache_get(f"analysis:{fid}")
        if a:
            hours += float(a.get("estimated_study_hours", 1))
    if hours == 0:
        hours = 2.0
    if item["kind"] == "assignment":
        hours += 1.0
    return max(1.5, min(hours, 6.0))


def split_sessions(hours):
    total_min = int(hours * 60)
    n = max(1, math.ceil(total_min / 90))
    length = max(45, min(90, round(total_min / n / 15) * 15))
    return n, length


def _pick(slots, n, length, one_per_day=True):
    """Pick n sessions, working backward from the deadline, spread over different days."""
    chosen, used_days = [], set()
    for s, e in sorted(slots, key=lambda x: x[0], reverse=True):
        if len(chosen) >= n:
            break
        if one_per_day and s.date() in used_days:
            continue
        need = timedelta(minutes=length)
        start = max(s, s.replace(hour=PREFERRED_START_HOUR, minute=0, second=0, microsecond=0))
        if start + need > e:
            start = s  # evening doesn't fit, use the start of the free slot
        if start + need <= e:
            chosen.append((start, start + need))
            used_days.add(s.date())
    return chosen


def create_study_plan(assessment_id, reason=""):
    item = st.get_item(assessment_id)
    if not item or not item["due"]:
        log("Planner", f"Can't plan '{item['title'] if item else assessment_id}' — no due date. "
                       "Asking the student.", "warn")
        return {"ok": False, "reason": "missing_due"}
    due = datetime.fromisoformat(item["due"])
    now = datetime.now(timezone.utc) + timedelta(minutes=15)
    if due <= now:
        return {"ok": False, "reason": "past_due"}

    hours = estimate_hours(item)
    n, length = split_sessions(hours)
    course = st.course_name(item["course_id"])
    log("Planner", f"'{item['title']}' needs ~{hours:g}h → {n} session(s) of {length} min.")

    # Try to finish a day early; fall back to "before the deadline".
    chosen = []
    for target in (due - timedelta(days=1), due - timedelta(hours=1)):
        slots = cal.get_free_slots(now, target)
        chosen = _pick(slots, n, length) or []
        if len(chosen) < n:
            chosen = _pick(slots, n, length, one_per_day=False)
        if len(chosen) >= n:
            break
    if not chosen:
        log("Planner", f"No free time left before '{item['title']}'. Suggest: shorten sessions, "
                       "study on the way, or use Panic mode.", "error")
        return {"ok": False, "reason": "no_free_slots"}
    if len(chosen) < n:
        log("Planner", f"Only found time for {len(chosen)}/{n} sessions before '{item['title']}'.",
            "warn")

    chosen.sort()
    for i, (s, e) in enumerate(chosen, 1):
        cal.create_study_event(item, course, s, e, i, len(chosen))
    when = ", ".join(s.strftime("%a %H:%M") for s, _ in chosen)
    log("Planner", f"📅 Booked {len(chosen)} {course} session(s) in Google Calendar: {when}.",
        "success")
    return {"ok": True, "sessions": len(chosen), "when": when}


def replan(assessment_id, reason=""):
    """Delete only StudyPilot's future events for this assessment, then plan again."""
    item = st.get_item(assessment_id)
    events = cal.list_studypilot_events(assessment_id)
    for ev in events:
        cal.delete_study_event(ev["id"])
    # forget local future sessions that were removed
    db.execute("DELETE FROM sessions WHERE assessment_id=? AND done=0 AND start>?",
               (assessment_id, datetime.now(timezone.utc).isoformat()))
    if events:
        log("Planner", f"Removed {len(events)} old session(s) for '{item['title']}'.")
    if item and item["active"]:
        return create_study_plan(assessment_id, reason)
    return {"ok": True, "sessions": 0}


def priority_score(item):
    """Higher = more urgent. Uses days left, type, difficulty and readiness."""
    dl = st.days_left(item["due"])
    if dl is None:
        return 0
    urgency = 10 / max(dl, 0.25)
    weight = 1.5 if item["kind"] == "quiz" else 1.0
    diff = 1.0
    for fid in st.lectures_for_assessment(item["id"]):
        a = db.cache_get(f"analysis:{fid}")
        if a:
            diff = max(diff, a.get("difficulty", 3) / 3)
    ready = st.readiness(item["id"])["score"] / 100
    return round(urgency * weight * diff * (1.2 - ready), 2)


def prioritize():
    items = [i for i in st.upcoming_items(14) if i["due"]]
    for i in items:
        i["priority"] = priority_score(i)
    return sorted(items, key=lambda i: i["priority"], reverse=True)


def plan_unplanned():
    """Plan every upcoming deadline that has no sessions yet, most urgent first."""
    for item in prioritize():
        has = db.one("SELECT 1 FROM sessions WHERE assessment_id=?", (item["id"],))
        if not has and (item["days_left"] or 0) > 0.1:
            try:
                create_study_plan(item["id"])
            except Exception as e:
                log("Planner", f"Calendar error while planning '{item['title']}': {e}", "error")
