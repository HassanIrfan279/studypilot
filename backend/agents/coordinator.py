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


def _is_recent(iso, days=30):
    if not iso:
        return False
    when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(when.tzinfo) - when).days <= days


def _analyze(file_id, title):
    try:
        st.analyze_lecture(file_id)
    except Exception as e:
        log("Tutor", f"Couldn't analyze '{title}': {e}", "warn")


def warm_up(max_files=8):
    """Analyze the lectures behind upcoming deadlines, build prep packs, then book study time.
    Runs after the first sync, and before a demo (pre-warms the cache)."""
    upcoming = sorted([i for i in st.upcoming_items(14) if i["due"]], key=lambda i: i["due"])
    log("Coordinator", f"{len(upcoming)} upcoming deadline(s). Asking Tutor to read their "
                       "lectures first.")
    targets = []
    for it in upcoming:
        for fid in st.lectures_for_assessment(it["id"], limit=3):
            if fid not in targets:
                targets.append(fid)
    for fid in targets[:max_files]:
        m = db.one("SELECT title FROM materials WHERE file_id=?", (fid,))
        _analyze(fid, m["title"] if m else fid)
    log("Coordinator", "Lectures ready. Asking Planner to book study time, most urgent first.")
    planner.plan_unplanned()
    for it in upcoming:
        try:
            st.build_prep_pack(it["id"])
        except Exception as e:
            log("Tutor", f"Prep pack for '{it['title']}' failed: {e}", "warn")
    db.cache_delete("brief")
    log("Coordinator", "✅ All set: lectures analyzed, study plan booked, prep packs ready.",
        "success")
    refresh()


def handle(result):
    changes, first = result["changes"], result["first_run"]

    if first:
        log("Coordinator", f"First sync: {result['courses']} courses, {result['materials']} files. "
                           "Plan: Tutor reads the lectures that matter now → Planner books study time.")
        refresh()
        warm_up()
        return

    if not changes:
        return

    spoken = []
    # 1) New lectures first — plans and prep packs depend on them
    for c in [c for c in changes if c["type"] == "new_material"]:
        m = c["material"]
        if not _is_recent(m.get("created")):
            continue
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
        reason = db.kv_get(f"cancel_reason:{it['id']}") or ""
        planner.replan(it["id"])
        past = it.get("due") and st.days_left(it["due"]) is not None and st.days_left(it["due"]) < 0
        if past:
            continue  # it just finished — nothing to announce
        log("Coordinator", f"'{it['title']}' was cancelled"
                           f"{f' (teacher: “{reason}”)' if reason else ' / removed from Classroom'}. "
                           "Cleared its study sessions.", "warn")
        spoken.append(f"{it['title']} in {st.course_name(it['course_id'])} was cancelled, "
                      "so I cleared its study sessions and freed up that time.")

    db.cache_delete("brief")
    for s in spoken:
        announce(s)
    refresh()
