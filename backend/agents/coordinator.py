"""Coordinator (root agent): looks at what the Sync agent found and decides which
sub-agent acts, in what order. Every decision is written to the activity log."""
from datetime import datetime
from zoneinfo import ZoneInfo

import db
from activity_log import announce, log, refresh
from agents import brain
from agents import planner_agent as planner
from config import AGENT_BRAIN, TIMEZONE
from tools import audit_tools as audit
from tools import calendar_tools as cal
from tools import study_tools as st
from tools import notify as tg  # WhatsApp (Twilio) + Telegram


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
    sync_deadline_markers()
    for it in upcoming:
        try:
            audit.audit_item(it)
        except Exception as e:
            log("Coordinator", f"Audit failed for '{it['title']}': {e}", "warn")
    for it in upcoming:
        try:
            st.build_prep_pack(it["id"])
        except Exception as e:
            log("Tutor", f"Prep pack for '{it['title']}' failed: {e}", "warn")
    from tools import notes_tools as notes
    for it in upcoming[:2]:  # detailed notes for the two nearest deadlines up front
        try:
            notes.generate_notes(it["id"])
        except Exception as e:
            log("Tutor", f"Notes for '{it['title']}' failed: {e}", "warn")
    notes.organize_drive(upcoming)
    db.cache_delete("brief")
    log("Coordinator", "✅ All set: lectures analyzed, study plan booked, prep packs and notes ready.",
        "success")
    refresh()


def sync_deadline_markers(items=None):
    """Put every upcoming deadline into Google Calendar as a '🎯 DUE' marker (instant, no AI)."""
    items = items if items is not None else [i for i in st.upcoming_items(30) if i["due"]]
    for it in items:
        try:
            res = cal.upsert_deadline_event(it, st.course_name(it["course_id"]))
            if res in ("created", "moved"):
                log("Planner", f"📅 Deadline marker {res} in Google Calendar: {it['title']} "
                               f"({_when(it['due'])}).", "success")
        except Exception as e:
            log("Planner", f"Couldn't update the Calendar marker for '{it['title']}': {e}", "warn")


def _situation(changes):
    lines = []
    for c in changes:
        it = c.get("item")
        if c["type"] == "added":
            lines.append(f"- NEW {it['kind']} item_id={it['id']} '{it['title']}' in "
                         f"{st.course_name(it['course_id'])}, due {_when(it['due'])}. "
                         f"Teacher's words: {it.get('description', '')[:200]}")
        elif c["type"] == "due_changed":
            lines.append(f"- MOVED item_id={it['id']} '{it['title']}' "
                         f"({st.course_name(it['course_id'])}) from {_when(c['old_due'])} to "
                         f"{_when(it['due'])}. Teacher's words: {it.get('description', '')[:200]}")
        elif c["type"] == "removed":
            reason = db.kv_get(f"cancel_reason:{it['id']}") or "removed from Classroom"
            lines.append(f"- CANCELLED item_id={it['id']} '{it['title']}' "
                         f"({st.course_name(it['course_id'])}). Reason: {reason}")
        elif c["type"] == "new_material" and _is_recent(c["material"].get("created")):
            m = c["material"]
            lines.append(f"- NEW LECTURE file_id={m['file_id']} '{m['title']}' in "
                         f"{st.course_name(m['course_id'])}")
    return "\n".join(lines)


def _title(changes):
    c = next((c for c in changes if c["type"] in ("due_changed", "added", "removed")), changes[0])
    if c["type"] == "new_material":
        return f"New lecture: {c['material']['title']}"
    verb = {"added": "New", "due_changed": "Moved", "removed": "Cancelled"}[c["type"]]
    return f"{verb}: {c['item']['title']} ({st.course_name(c['item']['course_id'])})"


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

    # 1) Instant: every deadline change goes into Google Calendar right now
    for c in changes:
        if c["type"] == "new_material":
            for row in db.query("SELECT id FROM items WHERE course_id=? AND active=1",
                                (c["material"]["course_id"],)):
                db.cache_delete(f"prep:{row['id']}")  # prep packs must include the new lecture
            continue
        it = c.get("item")
        if c["type"] in ("added", "due_changed") and it.get("due"):
            sync_deadline_markers([it])
        elif c["type"] == "removed":
            try:
                if cal.delete_deadline_event(it["id"]):
                    log("Planner", f"📅 Removed the deadline marker for '{it['title']}' from Calendar.")
            except Exception as e:
                log("Planner", f"Couldn't remove marker: {e}", "warn")
    refresh()

    # 2) Auditor: re-read the full source for every new/moved deadline before acting on it
    audit_notes = []
    for c in changes:
        if c["type"] in ("added", "due_changed"):
            try:
                issues = audit.audit_item(c["item"])
            except Exception as e:
                issues = []
                log("Coordinator", f"Audit failed for '{c['item']['title']}': {e}", "warn")
            if issues:
                audit_notes.append(f"- AUDITOR FLAGS for item_id={c['item']['id']}: " + " | ".join(issues))
    refresh()

    # 3) Gemini decides what to do about it (falls back to fixed rules if Gemini is down)
    situation = _situation(changes)
    if not situation:
        return
    if audit_notes:
        situation += ("\n\nThe auditor re-read the full source and raised these issues. If a date "
                      "looks wrong, ask the student before relying on it:\n" + "\n".join(audit_notes))
    if AGENT_BRAIN and brain.think_and_act("classroom", _title(changes),
                                           "Google Classroom just changed:\n" + situation):
        return
    _rule_based(changes)


def _rule_based(changes):
    """Backup plan: fixed pipeline used only if Gemini is unavailable."""
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
        tg.send(f"📘 <b>StudyPilot</b>\n{s}")
    refresh()
