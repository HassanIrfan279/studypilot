"""Coordinator (root agent): looks at what the Sync agent found and decides which
sub-agent acts, in what order. Every decision is written to the activity log."""
from datetime import datetime
from zoneinfo import ZoneInfo

import db
from activity_log import announce, log, refresh
from agents import planner_agent as planner
from config import TIMEZONE
from tools import study_tools as st


def _when(iso):
    if not iso:
        return "no date"
    return datetime.fromisoformat(iso).astimezone(ZoneInfo(TIMEZONE)).strftime("%a %d %b, %I:%M %p")


def _analyze(file_id, title):
    try:
        st.analyze_lecture(file_id)
    except Exception as e:
        log("Tutor", f"Couldn't analyze '{title}': {e}", "warn")


def handle(result):
    changes, first = result["changes"], result["first_run"]

    if first:
        log("Coordinator", f"First sync: {result['courses']} courses, {result['items']} deadlines, "
                           f"{result['materials']} lecture files. Plan: Tutor reads lectures → "
                           "Planner books study time.")
        for m in [c["material"] for c in changes if c["type"] == "new_material"]:
            _analyze(m["file_id"], m["title"])
        planner.plan_unplanned()
        db.cache_delete("brief")
        refresh()
        return

    if not changes:
        return

    spoken = []
    # 1) New lectures first — plans and prep packs depend on them
    for c in [c for c in changes if c["type"] == "new_material"]:
        m = c["material"]
        log("Coordinator", f"New lecture in {st.course_name(m['course_id'])}: '{m['title']}'. "
                           "Asking Tutor to analyze it.")
        _analyze(m["file_id"], m["title"])
        for row in db.query("SELECT id FROM items WHERE course_id=? AND active=1", (m["course_id"],)):
            db.cache_delete(f"prep:{row['id']}")

    # 2) New deadlines
    for c in [c for c in changes if c["type"] == "added"]:
        it = c["item"]
        course = st.course_name(it["course_id"])
        if not it["due"]:
            log("Coordinator", f"New {it['kind']} '{it['title']}' in {course} has no clear due "
                               "date — asking the student instead of guessing.", "warn")
            continue
        log("Coordinator", f"New {it['kind']} detected in {course}: '{it['title']}' "
                           f"(due {_when(it['due'])}). Asking Tutor to prepare, then Planner to "
                           "schedule.", "warn")
        try:
            st.build_prep_pack(it["id"], refresh=True)
        except Exception as e:
            log("Tutor", f"Prep pack failed: {e}", "warn")
        res = planner.create_study_plan(it["id"])
        msg = f"New {it['kind']} in {course}: {it['title']}, due {_when(it['due'])}."
        if res.get("ok"):
            msg += f" I've booked {res['sessions']} study sessions and made your prep pack."
        spoken.append(msg)

    # 3) Deadlines that moved -> re-plan
    for c in [c for c in changes if c["type"] == "due_changed"]:
        it = c["item"]
        course = st.course_name(it["course_id"])
        log("Coordinator", f"'{it['title']}' ({course}) moved from {_when(c['old_due'])} to "
                           f"{_when(it['due'])}. Asking Planner to re-plan.", "warn")
        res = planner.replan(it["id"], reason="due date changed")
        msg = f"Heads up! Your {course} {it['kind']}, {it['title']}, moved to {_when(it['due'])}."
        if res.get("ok"):
            msg += f" I've rearranged your plan: {res['sessions']} sessions, {res.get('when', '')}."
        spoken.append(msg)

    # 4) Removed deadlines -> clean up our events
    for c in [c for c in changes if c["type"] == "removed"]:
        it = c["item"]
        log("Coordinator", f"'{it['title']}' was removed from Classroom. Clearing its study "
                           "sessions.", "warn")
        planner.replan(it["id"])
        spoken.append(f"{it['title']} was cancelled, so I cleared its study sessions.")

    db.cache_delete("brief")
    for s in spoken:
        announce(s)
    refresh()
