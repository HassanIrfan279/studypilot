"""Closing the loop: the agent watches what the STUDENT does, not only the teacher.

- You add an event that clashes with a study session  -> the agent moves the session.
- A study session ends and you never marked it done     -> the agent reschedules it.
- You score badly on a practice quiz                    -> the agent books an extra,
                                                           focused session on your mistakes.
Each of these starts a Gemini agent run, with a rule-based backup.
"""
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import db
from activity_log import announce, log, refresh
from agents import brain
from config import AGENT_BRAIN, TIMEZONE
from tools import calendar_tools as cal
from tools import study_tools as st
from tools import notify as tg  # WhatsApp (Twilio) + Telegram

TZ = ZoneInfo(TIMEZONE)


def _fmt(dt):
    return dt.astimezone(TZ).strftime("%a %d %b %H:%M")


def _notify(msg):
    announce(msg)
    tg.send(f"📘 <b>StudyPilot</b>\n{msg}")


# ---------------- 1. calendar clashes ----------------
def check_clashes():
    now = datetime.now(timezone.utc)
    sessions = db.query("SELECT * FROM sessions WHERE done=0 AND start>?", (now.isoformat(),))
    if not sessions:
        return
    mine = cal.list_student_events(days=8)
    for s in sessions:
        s_start = datetime.fromisoformat(s["start"])
        s_end = datetime.fromisoformat(s["end"])
        for ev in mine:
            if ev["start"] < s_end and ev["end"] > s_start:
                key = f"clash:{s['event_id']}:{ev['id']}"
                if db.kv_get(key):
                    continue
                db.kv_set(key, True)
                _handle_clash(s, ev)
                break


def _handle_clash(s, ev):
    item = st.get_item(s["assessment_id"]) or {}
    situation = (f"The student added their own calendar event '{ev['title']}' "
                 f"({_fmt(ev['start'])}–{ev['end'].astimezone(TZ):%H:%M}). It clashes with the "
                 f"StudyPilot study session event_id={s['event_id']} for item_id={s['assessment_id']} "
                 f"('{item.get('title')}', due {item.get('due')}), booked {_fmt(datetime.fromisoformat(s['start']))}. "
                 "Respect the student's event: move the study session to the best free slot before "
                 "the deadline (prefer the same or next evening), verify, and tell the student.")
    if AGENT_BRAIN and brain.think_and_act("clash", f"Clash: {ev['title']} vs {item.get('title')}", situation):
        return
    # backup rule: next free slot of the same length
    length = int((datetime.fromisoformat(s["end"]) - datetime.fromisoformat(s["start"])).total_seconds() // 60)
    due = datetime.fromisoformat(item["due"]).astimezone(TZ) if item.get("due") else datetime.now(TZ) + timedelta(days=3)
    slot = cal.find_free_slot(length, ev["end"], due - timedelta(hours=1))
    if slot:
        cal.move_study_event(s["event_id"], slot[0])
        _notify(f"You added '{ev['title']}', so I moved your {item.get('title')} session to {_fmt(slot[0])}.")
    refresh()


# ---------------- 2. missed sessions ----------------
def check_missed():
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=15)).isoformat()
    recent = (now - timedelta(hours=6)).isoformat()  # ignore old history, only fresh misses
    for s in db.query("SELECT * FROM sessions WHERE done=0 AND end<? AND end>? ORDER BY end",
                      (cutoff, recent)):
        key = f"missed:{s['event_id']}"
        if db.kv_get(key):
            continue
        db.kv_set(key, True)
        item = st.get_item(s["assessment_id"])
        if not item or not item["active"] or st.days_left(item["due"]) is None or st.days_left(item["due"]) < 0.1:
            continue
        log("Coordinator", f"Study session for '{item['title']}' ended {_fmt(datetime.fromisoformat(s['end']))} "
                           "and was never marked done.", "warn")
        situation = (f"The student MISSED a study session for item_id={item['id']} '{item['title']}' "
                     f"(due {item['due']}). It was booked {_fmt(datetime.fromisoformat(s['start']))}–"
                     f"{datetime.fromisoformat(s['end']).astimezone(TZ):%H:%M} and never marked done. "
                     "Be strict but helpful: book a make-up session of the same length before the deadline, "
                     "verify it, and tell the student firmly that missed sessions lower readiness.")
        if AGENT_BRAIN and brain.think_and_act("missed", f"Missed session: {item['title']}", situation):
            return  # one missed-session run per tick keeps the feed readable
        length = int((datetime.fromisoformat(s["end"]) - datetime.fromisoformat(s["start"])).total_seconds() // 60)
        slot = cal.find_free_slot(length, datetime.now(TZ) + timedelta(minutes=30),
                                  datetime.fromisoformat(item["due"]).astimezone(TZ) - timedelta(hours=1))
        if slot:
            cal.create_study_event(item, st.course_name(item["course_id"]), slot[0], slot[1], 0, 0,
                                   focus="make-up for the missed session")
            _notify(f"You missed your {item['title']} session. I booked a make-up at {_fmt(slot[0])}. Don't skip this one.")
        refresh()
        return


# ---------------- 3. weak quiz result ----------------
def on_quiz_result(item_id, score, wrong_topics):
    if score >= 0.6:
        return
    item = st.get_item(item_id)
    if not item:
        return
    topics = ", ".join(wrong_topics[:4]) or "the topics you got wrong"
    # The notes always change after a weak attempt (in parallel with the re-plan)
    from tools import notes_tools as notes
    threading.Thread(target=notes.revise_for_weak, args=(item_id, wrong_topics), daemon=True).start()
    situation = (f"The student just scored {round(score * 100)}% on the practice quiz for "
                 f"item_id={item_id} '{item['title']}' (due {item['due']}). They got these wrong: "
                 f"{topics}. Act like a strict teacher: book ONE extra focused session on exactly those "
                 "topics before the deadline, verify it in the calendar, and tell the student what to "
                 "fix and that the next quiz attempt will have new questions. (Their study notes are already "
                 "being rewritten around these mistakes automatically — don't call rewrite_study_notes; "
                 "do mention the updated notes.)")
    if AGENT_BRAIN and brain.think_and_act("quiz", f"Weak quiz ({round(score * 100)}%): {item['title']}", situation):
        return
    due = datetime.fromisoformat(item["due"]).astimezone(TZ)
    slot = cal.find_free_slot(60, datetime.now(TZ) + timedelta(minutes=30), due - timedelta(hours=2))
    if slot:
        cal.create_study_event(item, st.course_name(item["course_id"]), slot[0], slot[1], 0, 0, focus=topics)
        _notify(f"{round(score * 100)}% isn't good enough. I booked an extra hour on {topics} at {_fmt(slot[0])}.")
    refresh()


def tick():
    """Called by the scheduler after every Classroom sync."""
    for check in (check_clashes, check_missed):
        try:
            check()
        except Exception as e:
            log("Coordinator", f"Watcher check failed: {e}", "warn")
