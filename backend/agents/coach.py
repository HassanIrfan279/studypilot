"""Coach: the agent's long-running, self-directed behaviour on top of the planner.

1. Habits     — learns WHEN the student actually studies (done vs missed by time of day) and
                moves future sessions there.
2. Goals      — per-course target grade; tracks readiness against it and sets how hard to push.
3. Reviewer   — a second agent that checks every calendar change (clashes, breaks, daily load,
                late nights, deadline) and can reject it.
4. Spaced     — wrong quiz topics come back as short review quizzes after 1, 3 and 7 days.
5. Tradeoffs  — when the week is overloaded, proposes what to cut/protect and ACTS ONLY AFTER
                the student approves (or revises it with their feedback).
6. Nightly    — every evening: reviews the day, learns, escalates unready deadlines
                (nudge -> extra session -> panic sheet + phone alert), checks overload, drafts a
                reschedule email (never sent) when two exams land on one day, and explains it all.
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel

import db
import gemini
import google_clients as g
import runs
from activity_log import announce, log, refresh
from config import FRONTEND_URL, TIMEZONE
from tools import calendar_tools as cal
from tools import notify
from tools import study_tools as st

TZ = ZoneInfo(TIMEZONE)
AGENT = "Coordinator"

db.execute("""CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT, assessment_id TEXT, topics TEXT, due_date TEXT,
    interval INTEGER, event_id TEXT, done INTEGER DEFAULT 0, score REAL, created REAL)""")
db.execute("""CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, title TEXT, message TEXT, plan TEXT,
    status TEXT, feedback TEXT, link TEXT, created REAL, decided REAL)""")


def _now():
    return datetime.now(TZ)


def _claim(key):
    """Do something only once (escalations, clash emails)."""
    if db.kv_get(f"once:{key}"):
        return False
    db.kv_set(f"once:{key}", time.time())
    return True


def _step(run_id, kind, text, level="info"):
    log(AGENT, text, level)
    runs.step(run_id, kind, text)


# =====================================================================  1. HABITS
BUCKETS = [("morning", 5, 12, 9), ("afternoon", 12, 17, 14), ("evening", 17, 21, 18), ("night", 21, 29, 21)]


def _bucket(dt):
    h = dt.hour if dt.hour >= 5 else dt.hour + 24
    for name, a, b, _ in BUCKETS:
        if a <= h < b:
            return name
    return "night"


def _bucket_range(day, name):
    """(start, end) of a time-of-day bucket on that day; 'night' ends at 23:59."""
    a, b = next((x[1], x[2]) for x in BUCKETS if x[0] == name)
    base = day.astimezone(TZ).replace(minute=0, second=0, microsecond=0)
    lo = base.replace(hour=a)
    hi = base.replace(hour=23, minute=59) if b >= 24 else base.replace(hour=b)
    return lo, hi


def habit_stats():
    """Completion rate by time of day and weekday, from sessions that have already ended."""
    since = (_now() - timedelta(days=45)).isoformat()
    cutoff = (_now() - timedelta(minutes=15)).isoformat()
    rows = db.query("SELECT start, done FROM sessions WHERE end < ? AND start > ?", (cutoff, since))
    by_bucket = {b[0]: {"done": 0, "total": 0} for b in BUCKETS}
    by_day = {}
    for r in rows:
        s = datetime.fromisoformat(r["start"]).astimezone(TZ)
        b = by_bucket[_bucket(s)]
        b["total"] += 1
        b["done"] += 1 if r["done"] else 0
        d = by_day.setdefault(s.strftime("%a"), {"done": 0, "total": 0})
        d["total"] += 1
        d["done"] += 1 if r["done"] else 0
    for v in list(by_bucket.values()) + list(by_day.values()):
        v["rate"] = round(v["done"] / v["total"], 2) if v["total"] else None
    pref = db.kv_get("habit_pref")
    return {"sessions": len(rows), "by_time": by_bucket, "by_day": by_day, "preference": pref,
            "learning": len(rows) < 6}


def preferred_hour(default=17):
    pref = db.kv_get("habit_pref")
    return pref["hour"] if pref else default


def adapt_habits(run_id=None):
    """If one time of day clearly works better, prefer it and move upcoming sessions there."""
    s = habit_stats()
    if s["learning"]:
        _step(run_id, "think", f"Habits: only {s['sessions']} finished session(s) so far — still learning "
                               "when you study best (need 6).")
        return None
    rated = [(k, v) for k, v in s["by_time"].items() if v["total"] >= 3 and v["rate"] is not None]
    if len(rated) < 2:
        _step(run_id, "think", "Habits: not enough variety in session times yet to compare.")
        return None
    best = max(rated, key=lambda kv: kv[1]["rate"])
    worst = min(rated, key=lambda kv: kv[1]["rate"])
    if best[1]["rate"] - worst[1]["rate"] < 0.3 or best[1]["rate"] < 0.6:
        _step(run_id, "think", f"Habits: no clear pattern yet (best {best[0]} {int(best[1]['rate'] * 100)}%, "
                               f"worst {worst[0]} {int(worst[1]['rate'] * 100)}%).")
        return None
    hour = next(b[3] for b in BUCKETS if b[0] == best[0])
    db.kv_set("habit_pref", {"bucket": best[0], "hour": hour, "since": time.time()})
    moved = []
    upcoming = db.query("SELECT * FROM sessions WHERE done=0 AND start > ? AND start < ? ORDER BY start",
                        ((_now() + timedelta(hours=1)).isoformat(), (_now() + timedelta(days=7)).isoformat()))
    for sess in upcoming:
        if len(moved) >= 4:
            break
        start = datetime.fromisoformat(sess["start"]).astimezone(TZ)
        if _bucket(start) != worst[0]:
            continue
        item = st.get_item(sess["assessment_id"])
        if not item or not item["due"]:
            continue
        length = int((datetime.fromisoformat(sess["end"]) - datetime.fromisoformat(sess["start"])).total_seconds() // 60)
        due = datetime.fromisoformat(item["due"]).astimezone(TZ) - timedelta(hours=1)
        for day_off in range(0, 3):
            lo, hi = _bucket_range(start + timedelta(days=day_off), best[0])
            lo, hi = max(_now() + timedelta(minutes=30), lo), min(due, hi)
            slot = cal.find_free_slot(length, lo, hi, prefer_evening=False) if hi > lo else None
            if slot and reviewer_check(slot[0], slot[1], item, run_id=run_id, ignore_event=sess["event_id"])["ok"]:
                cal.move_study_event(sess["event_id"], slot[0])
                moved.append(f"{item['title']} → {slot[0]:%a %H:%M}")
                break
    msg = (f"You finish {int(best[1]['rate'] * 100)}% of {best[0]} sessions but only "
           f"{int(worst[1]['rate'] * 100)}% of {worst[0]} ones, so I'll plan in the {best[0]} from now on"
           + (f" and moved {len(moved)} upcoming session(s): {'; '.join(moved)}." if moved else "."))
    _step(run_id, "say", "Habits: " + msg, "success")
    return msg


# =====================================================================  2. GOALS
TARGETS = {"A": 85, "B+": 75, "B": 70, "C": 55}


def goals():
    return db.kv_get("goals") or {}


def set_goal(course_id, grade):
    gl = goals()
    if grade in TARGETS:
        gl[course_id] = grade
    else:
        gl.pop(course_id, None)
    db.kv_set("goals", gl)
    log(AGENT, f"🎯 Goal set: {grade or 'none'} in {st.course_name(course_id)}.", "success")
    return goal_status()


def target_for(course_id, default=60):
    gr = goals().get(course_id)
    return TARGETS.get(gr, default)


def goal_status():
    out = []
    gl = goals()
    now = datetime.now(timezone.utc).isoformat()
    for c in db.query("SELECT id, name FROM courses ORDER BY name"):
        items = db.query("SELECT id FROM items WHERE course_id=? AND active=1 AND due > ?", (c["id"], now))
        scores = [st.readiness(i["id"])["score"] for i in items]
        current = round(sum(scores) / len(scores)) if scores else None
        grade = gl.get(c["id"])
        target = TARGETS.get(grade)
        gap = (target - current) if (target and current is not None) else None
        push = "steady"
        if gap is not None:
            push = "light" if gap <= 0 else "steady" if gap <= 15 else "hard"
        out.append({"course_id": c["id"], "course": c["name"], "goal": grade or "", "target": target,
                    "current": current, "upcoming": len(items), "gap": gap, "push": push})
    return out


def intensity(course_id):
    """Multiplier on study hours: pushes harder when the student is behind their goal."""
    for c in goal_status():
        if c["course_id"] == course_id:
            return {"light": 1.0, "steady": 1.15, "hard": 1.35}[c["push"]] if c["goal"] else 1.0
    return 1.0


# =====================================================================  3. REVIEWER AGENT
MAX_DAY_MIN = 360       # at most 6h of StudyPilot sessions in one day (exam weeks are heavy)
MIN_BREAK = 15          # minutes between two sessions
EARLIEST, LATEST = 7, 24


def reviewer_check(start, end, item=None, run_id=None, ignore_event=None, quiet=False):
    """Second agent: approve or reject a proposed session. Returns {ok, reasons}."""
    reasons = []
    start, end = start.astimezone(TZ), end.astimezone(TZ)
    if start < _now() + timedelta(minutes=5):
        reasons.append("it starts in the past")
    if start.hour < EARLIEST or (end.hour == 0 and end.minute > 0) or end.date() > start.date():
        reasons.append("it runs after midnight or before 7 AM — sleep matters")
    if item and item["due"] and end > datetime.fromisoformat(item["due"]).astimezone(TZ) - timedelta(minutes=30):
        reasons.append("it ends too close to (or after) the deadline")
    try:  # real clash check against every calendar event (except the one being moved)
        evs = g.with_retry(lambda: g.calendar().events().list(
            calendarId="primary", timeMin=start.isoformat(), timeMax=end.isoformat(),
            singleEvents=True, maxResults=20).execute()).get("items", [])
        clash = [e.get("summary", "an event") for e in evs if e["id"] != ignore_event
                 and e.get("start", {}).get("dateTime") and e.get("transparency") != "transparent"]
        if clash:
            reasons.append(f"it clashes with “{clash[0]}”")
    except Exception:
        pass
    day_rows = db.query("SELECT event_id, start, end FROM sessions WHERE substr(start,1,10)=?",
                        (start.strftime("%Y-%m-%d"),))
    mins = sum((datetime.fromisoformat(r["end"]) - datetime.fromisoformat(r["start"])).total_seconds() / 60
               for r in day_rows if r["event_id"] != ignore_event)
    if mins + (end - start).total_seconds() / 60 > MAX_DAY_MIN:
        reasons.append(f"that day would have over {MAX_DAY_MIN // 60}h of study")
    for r in day_rows:
        if r["event_id"] == ignore_event:
            continue
        s2 = datetime.fromisoformat(r["start"]).astimezone(TZ)
        e2 = datetime.fromisoformat(r["end"]).astimezone(TZ)
        if start < e2 + timedelta(minutes=MIN_BREAK) and end > s2 - timedelta(minutes=MIN_BREAK):
            reasons.append("no break between it and another session")
            break
    ok = not reasons
    if not quiet:
        when = f"{start:%a %d %b %H:%M}–{end:%H:%M}"
        text = (f"🛡 Reviewer approved {when}: no clashes, breaks and daily load OK." if ok
                else f"🛡 Reviewer rejected {when}: " + "; ".join(reasons) + ".")
        runs.step(run_id or _current_brain_run(), "review", text)
        if not ok:
            log("Reviewer", text, "warn")
    return {"ok": ok, "reasons": reasons}


def _current_brain_run():
    try:
        from agents import brain
        return getattr(brain._ctx, "run_id", None)
    except Exception:
        return None


def reviewed_slot(minutes, after, before, item, run_id=None, tries=5):
    """find_free_slot + Reviewer: if the reviewer rejects a slot, look again after it."""
    cursor = after
    for _ in range(max(tries, 8)):
        slot = cal.find_free_slot(minutes, cursor, before, prefer_evening=True)
        if not slot:
            return None
        verdict = reviewer_check(slot[0], slot[1], item, run_id=run_id, quiet=True)
        if verdict["ok"]:
            reviewer_check(slot[0], slot[1], item, run_id=run_id)  # log the approval
            return slot
        text = "; ".join(verdict["reasons"])
        runs.step(run_id or _current_brain_run(), "review",
                  f"🛡 Reviewer rejected {slot[0]:%a %H:%M}: {text}. Looking again…")
        if "over" in text and "of study" in text:        # day is full -> try tomorrow
            nxt = (slot[0] + timedelta(days=1)).replace(hour=0, minute=0)
            cursor = max(nxt, cursor + timedelta(minutes=MIN_BREAK))
        elif "no break" in text:                          # just too close -> leave a gap
            cursor = slot[0] + timedelta(minutes=MIN_BREAK + 15)
        else:
            cursor = slot[1] + timedelta(minutes=MIN_BREAK)
    return None


def review_plan(item_id, run_id=None):
    """Audit every future session of one deadline (after the planner booked them)."""
    rows = db.query("SELECT * FROM sessions WHERE assessment_id=? AND start > ? ORDER BY start",
                    (item_id, _now().isoformat()))
    item = st.get_item(item_id)
    problems = []
    for r in rows:
        v = reviewer_check(datetime.fromisoformat(r["start"]), datetime.fromisoformat(r["end"]), item,
                           ignore_event=r["event_id"], quiet=True)
        if not v["ok"]:
            problems.append(f"{datetime.fromisoformat(r['start']).astimezone(TZ):%a %H:%M}: {'; '.join(v['reasons'])}")
    text = (f"🛡 Reviewer checked {len(rows)} session(s): all fine." if not problems
            else "🛡 Reviewer found problems — " + " | ".join(problems))
    runs.step(run_id or _current_brain_run(), "review", text)
    return {"checked": len(rows), "problems": problems}


# =====================================================================  4. SPACED REPETITION
INTERVALS = (1, 3, 7)


def schedule_reviews(assessment_id, wrong):
    """Topics the student got wrong come back after 1, 3 and 7 days (20-min review quizzes)."""
    wrong = [w for w in (wrong or []) if w][:6]
    item = st.get_item(assessment_id)
    if not wrong or not item:
        return []
    for old in db.query("SELECT * FROM reviews WHERE assessment_id=? AND done=0", (assessment_id,)):
        if old["event_id"]:
            try:
                g.calendar().events().delete(calendarId="primary", eventId=old["event_id"]).execute()
            except Exception:
                pass
        db.execute("DELETE FROM reviews WHERE id=?", (old["id"],))
    try:
        topics = gemini.generate_json(
            "Name the 1-3 underlying concepts these wrong quiz questions test, as short topic names.\n"
            + "\n".join(f"- {w}" for w in wrong), _Topics)["topics"][:3]
    except Exception:
        topics = [w[:60] for w in wrong[:2]]
    booked = []
    course = cal.nice_course(st.course_name(item["course_id"]))
    win_s, win_e = cal._study_window()
    for d in INTERVALS:
        day = (_now() + timedelta(days=d)).date()
        lo = max(_now() + timedelta(minutes=30), datetime.combine(day, win_s, TZ))
        hi = datetime.combine(day, win_e, TZ)
        rid = db.execute("INSERT INTO reviews(assessment_id, topics, due_date, interval, created) VALUES (?,?,?,?,?)",
                         (assessment_id, json.dumps(topics), day.isoformat(), d, time.time()))
        slot = cal.find_free_slot(20, lo, hi, prefer_evening=True)
        if slot:
            body = {"summary": f"🔁 Review ({d}d): {', '.join(topics)[:60]} · {course}",
                    "description": f"StudyPilot spaced review — a 4-question quiz on what you got wrong.\n"
                                   f"Open: {FRONTEND_URL}/review/{rid}",
                    "start": {"dateTime": slot[0].isoformat(), "timeZone": TIMEZONE},
                    "end": {"dateTime": slot[1].isoformat(), "timeZone": TIMEZONE},
                    "colorId": "7",
                    "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 5}]},
                    "extendedProperties": {"private": {"studypilot": "true", "kind": "review", "review_id": str(rid)}}}
            ev = cal._insert_once(g.calendar(), body)
            db.execute("UPDATE reviews SET event_id=? WHERE id=?", (ev["id"], rid))
            booked.append(f"{slot[0]:%a %H:%M}")
    log("Tutor", f"🔁 Spaced repetition: {', '.join(topics)} will come back as short review quizzes "
                 f"in 1, 3 and 7 days ({', '.join(booked) or 'times to be picked'}).", "success")
    refresh()
    return booked


class _Topics(BaseModel):
    topics: list[str]


def reviews(upcoming_only=True):
    rows = db.query("SELECT * FROM reviews " + ("WHERE done=0 " if upcoming_only else "") + "ORDER BY due_date, id")
    out = []
    for r in rows:
        item = st.get_item(r["assessment_id"])
        out.append({**dict(r), "topics": json.loads(r["topics"] or "[]"),
                    "title": item["title"] if item else "", "course": st.course_name(item["course_id"]) if item else "",
                    "due_now": r["due_date"] <= _now().date().isoformat()})
    return out


def review_quiz(review_id):
    r = db.one("SELECT * FROM reviews WHERE id=?", (review_id,))
    if not r:
        return None
    key = f"reviewquiz:{review_id}"
    cached = db.cache_get(key)
    if cached:
        return cached
    topics = json.loads(r["topics"] or "[]")
    analyses = st._analyses(st.lectures_for_assessment(r["assessment_id"]))
    quiz = gemini.generate_json(
        f"Spaced-repetition review (day {r['interval']}): write exactly 4 multiple-choice questions "
        f"(4 options, one correct, one-sentence explanation) that re-test ONLY these concepts the "
        f"student got wrong before: {', '.join(topics)}. Use new angles and numbers.\n\n"
        + st._material_text(analyses), st.Quiz, system=st.TUTOR_SYSTEM)
    out = {"review": {**dict(r), "topics": topics}, "quiz": quiz}
    db.cache_set(key, out)
    return out


def review_result(review_id, score):
    r = db.one("SELECT * FROM reviews WHERE id=?", (review_id,))
    if not r:
        return None
    db.execute("UPDATE reviews SET done=1, score=? WHERE id=?", (score, review_id))
    topics = json.loads(r["topics"] or "[]")
    if score < 0.6:  # not stuck yet -> one more review soon
        day = (_now() + timedelta(days=2)).date()
        db.execute("INSERT INTO reviews(assessment_id, topics, due_date, interval, created) VALUES (?,?,?,?,?)",
                   (r["assessment_id"], r["topics"], day.isoformat(), 2, time.time()))
        log("Tutor", f"🔁 Review {round(score * 100)}% on {', '.join(topics)} — not solid yet, it comes back in 2 days.", "warn")
    else:
        log("Tutor", f"🔁 Review {round(score * 100)}% on {', '.join(topics)} — it's sticking.", "success")
    refresh()
    return {"ok": True}


# =====================================================================  5. TRADEOFFS (ask first)
class Change(BaseModel):
    item_id: str
    sessions: int
    minutes_each: int
    reason: str


class Tradeoff(BaseModel):
    message: str
    changes: list[Change]


def workload(days=7):
    now = _now()
    end = now + timedelta(days=days)
    from agents import planner_agent as planner
    rows = db.query("SELECT * FROM items WHERE active=1 AND due > ? AND due < ? ORDER BY due",
                    (now.isoformat(), end.isoformat()))
    items, need_total = [], 0.0
    for it in rows:
        need = planner.estimate_hours(it)
        done_h = sum((datetime.fromisoformat(s["end"]) - datetime.fromisoformat(s["start"])).total_seconds() / 3600
                     for s in db.query("SELECT * FROM sessions WHERE assessment_id=? AND done=1", (it["id"],)))
        fut = db.query("SELECT * FROM sessions WHERE assessment_id=? AND start > ? ORDER BY start", (it["id"], now.isoformat()))
        booked_h = sum((datetime.fromisoformat(s["end"]) - datetime.fromisoformat(s["start"])).total_seconds() / 3600 for s in fut)
        remaining = max(0.0, need - done_h)
        need_total += remaining
        items.append({"item_id": it["id"], "title": it["title"], "kind": it["kind"],
                      "course": st.course_name(it["course_id"]), "due": it["due"][:16],
                      "days_left": round(st.days_left(it["due"]) or 0, 1),
                      "readiness": st.readiness(it["id"])["score"], "target": target_for(it["course_id"]),
                      "need_hours": round(remaining, 1), "booked_sessions": len(fut),
                      "booked_hours": round(booked_h, 1)})
    free = sum((e - s).total_seconds() / 3600 for s, e in cal.get_free_slots(now + timedelta(minutes=30), end))
    booked_total = sum(i["booked_hours"] for i in items)
    # Free time already contains the booked sessions? No: booked sessions are busy in freebusy.
    available = free + booked_total
    return {"items": items, "need_hours": round(need_total, 1), "available_hours": round(available, 1),
            "free_hours": round(free, 1), "overloaded": need_total > available * 0.7}


def pending_proposals():
    return [{**dict(p), "plan": json.loads(p["plan"] or "null")}
            for p in db.query("SELECT * FROM proposals WHERE status='pending' ORDER BY id DESC")]


def propose_tradeoff(feedback="", run_id=None, force=False):
    w = workload()
    if not w["overloaded"] and not force:
        msg = (f"Workload check: you need ~{w['need_hours']}h this week and have ~{w['available_hours']}h "
               "of study time. No tradeoffs needed.")
        _step(run_id, "think", msg)
        return {"overloaded": False, "message": msg, "workload": w}
    _step(run_id, "think", f"Overloaded: ~{w['need_hours']}h needed vs ~{w['available_hours']}h available this week. "
                           "Deciding what matters most…", "warn")
    plan = gemini.generate_json(
        "The student is overloaded this week. Decide how to split the limited study time. Weigh: how "
        "close each deadline is, how far readiness is below the student's target, and how much the "
        "item likely counts (exams/quizzes and big assignments matter more). Protect what matters, cut "
        "what's safest to cut. For EVERY item give the new number of future sessions (0-4) and "
        "minutes_each (45, 60 or 90). Total hours must fit in the available hours. message: 2-3 short "
        "sentences to the student in the first person, naming concrete numbers, e.g. \"I'll cut the CN "
        "assignment from 3 sessions to 2 and protect Quiz 3, because you're at 40% readiness there.\""
        + (f"\nThe student rejected the previous proposal and said: {feedback}" if feedback else "")
        + f"\n\nAvailable hours: {w['available_hours']}\nITEMS:\n{json.dumps(w['items'], ensure_ascii=False)}",
        Tradeoff, system="You are StudyPilot's planning agent: strict, fair and transparent.")
    valid = {i["item_id"] for i in w["items"]}
    plan["changes"] = [c for c in plan["changes"] if c["item_id"] in valid]
    for p in pending_proposals():
        if p["kind"] == "tradeoff":
            db.execute("UPDATE proposals SET status='replaced', decided=? WHERE id=?", (time.time(), p["id"]))
    pid = db.execute("INSERT INTO proposals(kind, title, message, plan, status, feedback, created) VALUES (?,?,?,?,?,?,?)",
                     ("tradeoff", "Your week is overloaded", plan["message"], json.dumps({**plan, "workload": w}),
                      "pending", feedback, time.time()))
    _step(run_id, "ask", f"Asked you to approve: {plan['message']}")
    announce(plan["message"] + " Approve it on the dashboard?")
    notify.send("⚖️ StudyPilot needs your OK: " + plan["message"])
    refresh()
    return {"overloaded": True, "proposal_id": pid, "message": plan["message"]}


def decide(pid, action, feedback=""):
    p = db.one("SELECT * FROM proposals WHERE id=?", (pid,))
    if not p or p["status"] != "pending":
        raise ValueError("This proposal is no longer open.")
    if action == "dismiss":
        db.execute("UPDATE proposals SET status='dismissed', decided=? WHERE id=?", (time.time(), pid))
        log(AGENT, "Okay — I'll leave your plan as it is.")
        refresh()
        return {"ok": True}
    if action == "change":
        db.execute("UPDATE proposals SET status='revised', feedback=?, decided=? WHERE id=?", (feedback, time.time(), pid))
        log(AGENT, f"Rethinking the plan with your feedback: “{feedback[:100]}”")
        return propose_tradeoff(feedback=feedback, force=True)
    if action != "approve":
        raise ValueError("Unknown action")
    plan = json.loads(p["plan"])
    run_id = runs.start("tradeoff", "Applying the plan you approved")
    applied = []
    for ch in plan["changes"]:
        item = st.get_item(ch["item_id"])
        if not item:
            continue
        fut = db.query("SELECT * FROM sessions WHERE assessment_id=? AND start > ? ORDER BY start",
                       (ch["item_id"], _now().isoformat()))
        want = max(0, min(4, int(ch["sessions"])))
        if len(fut) > want:
            for s in fut[want:]:   # drop the latest ones first
                try:
                    cal.delete_study_event(s["event_id"])
                except Exception:
                    pass
            applied.append(f"{item['title']}: {len(fut)} → {want}")
        elif len(fut) < want:
            due = datetime.fromisoformat(item["due"]).astimezone(TZ) - timedelta(hours=1)
            added = 0
            for _ in range(want - len(fut)):
                slot = reviewed_slot(int(ch["minutes_each"] or 60), _now() + timedelta(minutes=30), due, item, run_id)
                if not slot:
                    break
                cal.create_study_event(item, st.course_name(item["course_id"]), slot[0], slot[1], 0, 0,
                                       focus=ch["reason"][:60])
                added += 1
            applied.append(f"{item['title']}: {len(fut)} → {len(fut) + added}")
        runs.step(run_id, "act", f"{item['title']}: {ch['reason']}")
    db.execute("UPDATE proposals SET status='approved', decided=? WHERE id=?", (time.time(), pid))
    summary = "Applied your approved plan: " + ("; ".join(applied) if applied else "no calendar changes needed") + "."
    runs.finish(run_id, "done", summary)
    log(AGENT, "✅ " + summary, "success")
    refresh()
    return {"ok": True, "applied": applied}


# =====================================================================  6. NIGHTLY REVIEW
class EmailDraft(BaseModel):
    ask_to_move_item_id: str
    subject: str
    body: str


def _exam_clashes(run_id):
    """Two quizzes/exams on the same day -> a polite reschedule request as a Gmail DRAFT."""
    from agents import career_agent as career
    rows = db.query("SELECT * FROM items WHERE active=1 AND kind='quiz' AND due > ? ORDER BY due",
                    (_now().isoformat(),))
    by_day = {}
    for r in rows:
        by_day.setdefault(datetime.fromisoformat(r["due"]).astimezone(TZ).date(), []).append(r)
    made = []
    for day, items in by_day.items():
        if len(items) < 2:
            continue
        a, b = items[0], items[1]
        if not _claim(f"clashmail:{a['id']}:{b['id']}"):
            continue
        prof = db.kv_get("profile") or {}
        name = prof.get("name") or (career.profile() or {}).get("name") or ""
        d = gemini.generate_json(
            "Two assessments fall on the same day. Choose the one that is more reasonable to ask the "
            "teacher to move (prefer the smaller quiz, or the course whose teacher is likely flexible) and "
            "write a short, polite, respectful email (80-120 words) from the student to that course's "
            "teacher asking whether it could be moved by a day or two, mentioning the other assessment. "
            f"Sign as {name or 'the student'}. No guilt-tripping, no excuses.\n\n"
            f"A: id={a['id']} {a['title']} — {st.course_name(a['course_id'])}, {a['due']}\n"
            f"B: id={b['id']} {b['title']} — {st.course_name(b['course_id'])}, {b['due']}", EmailDraft)
        link, note = "", ""
        if career.has_compose():
            try:
                _, link = career._draft("", d["subject"], d["body"], attach_cv=False)
            except Exception as e:
                note = f" (couldn't create the Gmail draft: {type(e).__name__})"
        moved = a if d["ask_to_move_item_id"] == a["id"] else b
        msg = (f"{a['title']} and {b['title']} are both on {day:%a %d %b}. I drafted a polite email asking the "
               f"{st.course_name(moved['course_id'])} teacher to move {moved['title']} — it's in your Gmail "
               f"drafts; add their address and send it only if you want to.{note}")
        db.execute("INSERT INTO proposals(kind, title, message, plan, status, link, created) VALUES (?,?,?,?,?,?,?)",
                   ("email", "Two exams on one day", msg, json.dumps(d), "pending", link, time.time()))
        _step(run_id, "say", "📧 " + msg, "warn")
        notify.send("📧 StudyPilot: " + msg)
        made.append(msg)
    return made


def _escalate(run_id):
    """Deadline close + not ready: 3 days -> nudge, 2 days -> extra session, 1 day -> panic sheet."""
    acts = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for it in db.query("SELECT * FROM items WHERE active=1 AND due > ? ORDER BY due", (now_iso,)):
        dl = st.days_left(it["due"])
        if dl is None or dl > 3.2:
            continue
        ready = st.readiness(it["id"])["score"]
        target = target_for(it["course_id"])
        if ready >= target:
            continue
        name = f"{it['title']} ({st.course_name(it['course_id'])})"
        if dl <= 1.2:
            if _claim(f"esc:{it['id']}:panic"):
                try:
                    st.panic_mode(it["id"])
                except Exception:
                    pass
                msg = (f"🚨 {name} is due in {max(1, round(dl * 24))}h and you're at {ready}% (target {target}%). "
                       f"Your 20-minute cram sheet is ready: {FRONTEND_URL}/panic/{it['id']}")
                notify.send("StudyPilot: " + msg)
                _step(run_id, "say", msg, "error")
                acts.append(msg)
        elif dl <= 2.2:
            if _claim(f"esc:{it['id']}:extra"):
                due = datetime.fromisoformat(it["due"]).astimezone(TZ) - timedelta(hours=2)
                slot = reviewed_slot(60, _now() + timedelta(minutes=30), due, it, run_id)
                if slot:
                    cal.create_study_event(it, st.course_name(it["course_id"]), slot[0], slot[1], 0, 0,
                                           focus="catch-up: readiness below your goal")
                    msg = f"⏫ {name} is 2 days away at {ready}% readiness — I added an extra hour {slot[0]:%a %H:%M}."
                else:
                    msg = f"⏫ {name} is 2 days away at {ready}% readiness, and there's no free hour left — use Panic mode."
                _step(run_id, "act", msg, "warn")
                acts.append(msg)
        else:
            if _claim(f"esc:{it['id']}:nudge"):
                msg = f"👀 {name} is 3 days away and you're at {ready}% (goal {target}%). Do one session and the practice quiz tomorrow."
                notify.send("StudyPilot: " + msg)
                _step(run_id, "say", msg)
                acts.append(msg)
    if not acts:
        _step(run_id, "think", "Escalation: every close deadline is on track (or already escalated).")
    return acts


def _today(run_id):
    start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.query("SELECT * FROM sessions WHERE start >= ? AND start < ?",
                    (start.isoformat(), (start + timedelta(days=1)).isoformat()))
    done = sum(1 for r in rows if r["done"])
    past = [r for r in rows if datetime.fromisoformat(r["end"]) < _now()]
    missed = sum(1 for r in past if not r["done"])
    quizzes = db.query("SELECT assessment_id, score FROM quiz_results WHERE ts >= ?", (start.timestamp(),))
    q = ", ".join(f"{(st.get_item(r['assessment_id']) or {'title': '?'})['title']} {round(r['score'] * 100)}%" for r in quizzes)
    text = f"Today: {done} session(s) done, {missed} missed, {len(rows) - len(past)} still ahead" + (f"; quizzes: {q}" if q else "") + "."
    _step(run_id, "think", text)
    return {"done": done, "missed": missed, "quizzes": q}


_review_lock = threading.Lock()


def nightly_review(trigger="schedule"):
    if not _review_lock.acquire(blocking=False):
        return {"busy": True}
    run_id = runs.start("review", "Nightly review" if trigger == "schedule" else "Review (run now)")
    notes = []
    try:
        today = _today(run_id)
        for name, fn in (("habits", lambda: adapt_habits(run_id)), ("escalation", lambda: _escalate(run_id)),
                         ("workload", lambda: propose_tradeoff(run_id=run_id)), ("exam clashes", lambda: _exam_clashes(run_id))):
            try:
                out = fn()
                if out:
                    notes.append({"part": name, "out": out})
            except Exception as e:
                _step(run_id, "warn", f"{name} check failed ({type(e).__name__}); skipped.", "warn")
        gs = [c for c in goal_status() if c["goal"]]
        if gs:
            _step(run_id, "think", "Goals: " + "; ".join(
                f"{c['course']} {c['current'] if c['current'] is not None else '–'}% vs {c['target']}% → push {c['push']}" for c in gs))
        tomorrow = (_now() + timedelta(days=1)).date().isoformat()
        sess_tom = db.query("SELECT title, start FROM sessions WHERE substr(start,1,10)=? ORDER BY start", (tomorrow,))
        rev_tom = db.query("SELECT topics FROM reviews WHERE due_date=? AND done=0", (tomorrow,))
        summary = gemini.generate_text(
            "Write tonight's review for the student in 3-4 short sentences, first person, honest and "
            "specific: how today went, what you changed and WHY, and what tomorrow looks like. No lists.\n\n"
            f"TODAY: {json.dumps(today)}\nACTIONS: {json.dumps(notes, default=str)[:3000]}\n"
            f"GOALS: {json.dumps(gs)[:1500]}\nTOMORROW'S SESSIONS: {[dict(s) for s in sess_tom]}\n"
            f"REVIEW QUIZZES TOMORROW: {len(rev_tom)}",
            system="You are StudyPilot, a strict but caring study coach: direct about problems, never "
                   "insulting or dramatic (no 'write-off', no 'panicked'), always ending with a clear next step.")
        db.kv_set("last_review", {"ts": time.time(), "text": summary, "date": _now().date().isoformat()})
        runs.step(run_id, "say", summary)
        runs.finish(run_id, "done", summary[:200])
        log(AGENT, "🌙 " + summary, "success")
        notify.send("🌙 StudyPilot nightly review: " + summary)
        refresh()
        return {"ok": True, "summary": summary}
    except Exception as e:
        runs.finish(run_id, "fallback", f"Review stopped: {type(e).__name__}")
        raise
    finally:
        _review_lock.release()


REVIEW_HOUR = 21  # 9 PM local, once a day


def tick():
    """Scheduler hook (cheap): run the nightly review once a day after REVIEW_HOUR."""
    now = _now()
    if now.hour >= REVIEW_HOUR and db.kv_get("review_ran_on") != now.date().isoformat():
        db.kv_set("review_ran_on", now.date().isoformat())
        nightly_review()
