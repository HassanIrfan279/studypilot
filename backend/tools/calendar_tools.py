"""Planner tools: Google Calendar free/busy + StudyPilot-owned study events.
RULE: we only ever edit/delete events tagged extendedProperties.private.studypilot = "true"."""
from datetime import datetime, timedelta, time as dtime, timezone
from zoneinfo import ZoneInfo

import db
import google_clients as g
from config import FRONTEND_URL, STUDY_WINDOW_END, STUDY_WINDOW_START, TIMEZONE

TZ = ZoneInfo(TIMEZONE)
# Google Calendar event colours (colorId 1-11); each course gets one
COURSE_COLORS = ["9", "10", "6", "3", "5", "11", "7", "2", "4", "1", "8"]
COLOR_HEX = {"1": "#7986cb", "2": "#33b679", "3": "#8e24aa", "4": "#e67c73", "5": "#f6bf26",
             "6": "#f4511e", "7": "#039be5", "8": "#616161", "9": "#3f51b5", "10": "#0b8043",
             "11": "#d50000"}


def course_color(course_id):
    row = db.one("SELECT color FROM courses WHERE id=?", (course_id,))
    idx = row["color"] if row and row["color"] is not None else 0
    return COURSE_COLORS[idx % len(COURSE_COLORS)]


def _hm(s):
    h, m = s.split(":")
    return dtime(int(h), int(m))


def _study_window():
    """Study window from the student's profile (wake +1h .. sleep -30min), else from .env."""
    p = db.kv_get("profile") or {}
    try:
        wake = datetime.combine(datetime.now().date(), _hm(p["wake_time"])) + timedelta(hours=1)
        sleep = datetime.combine(datetime.now().date(), _hm(p["sleep_time"])) - timedelta(minutes=30)
        if p["sleep_time"] < "05:00":  # sleeps after midnight -> study until 23:30
            sleep = datetime.combine(datetime.now().date(), dtime(23, 30))
        if sleep > wake:
            return wake.time(), sleep.time()
    except (KeyError, ValueError, TypeError):
        pass
    return _hm(STUDY_WINDOW_START), _hm(STUDY_WINDOW_END)


def get_free_slots(start: datetime, end: datetime):
    """Free time between start and end, only inside the daily study window. Returns [(s, e)]."""
    if end <= start:
        return []
    svc = g.calendar()
    body = {"timeMin": start.astimezone(timezone.utc).isoformat(),
            "timeMax": end.astimezone(timezone.utc).isoformat(),
            "timeZone": TIMEZONE, "items": [{"id": "primary"}]}
    resp = g.with_retry(lambda: svc.freebusy().query(body=body).execute())
    busy = [(datetime.fromisoformat(b["start"].replace("Z", "+00:00")).astimezone(TZ),
             datetime.fromisoformat(b["end"].replace("Z", "+00:00")).astimezone(TZ))
            for b in resp["calendars"]["primary"].get("busy", [])]
    busy.sort()

    win_start, win_end = _study_window()
    free = []
    day = start.astimezone(TZ).date()
    while day <= end.astimezone(TZ).date():
        w_start = datetime.combine(day, win_start, TZ)
        w_end = datetime.combine(day, win_end, TZ)
        cur, stop = max(w_start, start.astimezone(TZ)), min(w_end, end.astimezone(TZ))
        for b_s, b_e in busy:
            if b_e <= cur or b_s >= stop:
                continue
            if b_s > cur:
                free.append((cur, b_s))
            cur = max(cur, b_e)
        if cur < stop:
            free.append((cur, stop))
        day += timedelta(days=1)
    return [(s, e) for s, e in free if (e - s) >= timedelta(minutes=30)]


def nice_course(name):
    small = {"and", "of", "the", "in", "on", "for", "to", "a", "an"}
    return " ".join(w if i and w.lower() in small else (w if w[:1].isupper() else w.capitalize())
                    for i, w in enumerate((name or "").split()))


def _insert_once(svc, body):
    """Insert with a client-chosen event id, so a retry after a network timeout can never create
    a duplicate: Google answers 409 for the second insert and we just fetch the first one."""
    import uuid
    from googleapiclient.errors import HttpError
    body = {**body, "id": uuid.uuid4().hex}  # hex digits are valid Calendar event-id characters

    def go():
        try:
            return svc.events().insert(calendarId="primary", body=body).execute()
        except HttpError as e:
            if getattr(e.resp, "status", None) == 409:
                return svc.events().get(calendarId="primary", eventId=body["id"]).execute()
            raise
    return g.with_retry(go)


def create_study_event(item, course_name, start, end, idx, total, focus=None):
    svc = g.calendar()
    course_name = nice_course(course_name)
    if focus:
        short = focus if len(focus) <= 50 else focus[:48].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        title = f"📘 {nice_course(course_name)}: extra session on {short} ({item['title']})"
    else:
        title = f"📘 {course_name}: {item['title']} prep (Session {idx}/{total})"
    body = {
        "summary": title,
        "description": f"StudyPilot study session.\n{'Focus: ' + focus + chr(10) if focus else ''}"
                       f"Prep pack: {FRONTEND_URL}/prep/{item['id']}\n"
                       f"Classroom: {item.get('link', '')}",
        "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
        "colorId": course_color(item["course_id"]),
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]},
        "extendedProperties": {"private": {"studypilot": "true", "assessment_id": item["id"],
                                           "kind": "session"}},
    }
    ev = _insert_once(svc, body)
    db.execute("INSERT OR REPLACE INTO sessions(event_id, assessment_id, title, start, end, done) "
               "VALUES (?,?,?,?,?,0)", (ev["id"], item["id"], title, start.isoformat(),
                                        end.isoformat()))
    return ev


def list_studypilot_events(assessment_id=None, future_only=True, include_deadlines=False):
    """StudyPilot's own events. Study sessions only, unless include_deadlines=True."""
    svc = g.calendar()
    props = ["studypilot=true"] + ([f"assessment_id={assessment_id}"] if assessment_id else [])
    kwargs = {"calendarId": "primary", "privateExtendedProperty": props, "singleEvents": True,
              "orderBy": "startTime", "maxResults": 250}
    if future_only:
        kwargs["timeMin"] = datetime.now(timezone.utc).isoformat()
    items = g.with_retry(lambda: svc.events().list(**kwargs).execute()).get("items", [])
    if include_deadlines:
        return items
    return [e for e in items if _kind(e) != "deadline"]


def _kind(ev):
    return ev.get("extendedProperties", {}).get("private", {}).get("kind", "session")


# ---------- deadline markers: every deadline itself is visible in Google Calendar ----------
def upsert_deadline_event(item, course_name):
    """Create or move the '🎯 DUE' marker for a deadline. Transparent, so it never blocks
    study planning. Returns 'created' | 'moved' | 'unchanged'."""
    if not item.get("due"):
        return "skipped"
    svc = g.calendar()
    due = datetime.fromisoformat(item["due"]).astimezone(TZ)
    start = due - timedelta(minutes=30)
    body = {
        "summary": f"🎯 DUE: {item['title']} ({nice_course(course_name)})",
        "description": f"Deadline tracked by StudyPilot.\nPrep pack: {FRONTEND_URL}/prep/{item['id']}\n"
                       f"Source: {item.get('link', '')}",
        "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": due.isoformat(), "timeZone": TIMEZONE},
        "colorId": course_color(item["course_id"]),
        "transparency": "transparent",
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 24 * 60},
                                                         {"method": "popup", "minutes": 60}]},
        "extendedProperties": {"private": {"studypilot": "true", "assessment_id": item["id"],
                                           "kind": "deadline"}},
    }
    existing = [e for e in list_studypilot_events(item["id"], future_only=False, include_deadlines=True)
                if _kind(e) == "deadline"]
    if existing:
        ev = existing[0]
        if ev["start"].get("dateTime") and datetime.fromisoformat(ev["start"]["dateTime"]) == start \
                and ev.get("summary") == body["summary"]:
            return "unchanged"
        g.with_retry(lambda: svc.events().patch(calendarId="primary", eventId=ev["id"],
                                                body=body).execute())
        return "moved"
    _insert_once(svc, body)
    return "created"


def delete_deadline_event(item_id):
    svc = g.calendar()
    n = 0
    for ev in list_studypilot_events(item_id, future_only=False, include_deadlines=True):
        if _kind(ev) == "deadline":
            g.with_retry(lambda: svc.events().delete(calendarId="primary", eventId=ev["id"]).execute())
            n += 1
    return n


# ---------- the student's own calendar (for clash detection) ----------
def list_student_events(days=7):
    """Timed events the student created themselves (not StudyPilot's), next `days` days."""
    svc = g.calendar()
    now = datetime.now(timezone.utc)
    items = g.with_retry(lambda: svc.events().list(
        calendarId="primary", timeMin=now.isoformat(), timeMax=(now + timedelta(days=days)).isoformat(),
        singleEvents=True, orderBy="startTime", maxResults=250).execute()).get("items", [])
    out = []
    for e in items:
        if _is_ours(e) or "dateTime" not in e.get("start", {}) or e.get("transparency") == "transparent":
            continue
        out.append({"id": e["id"], "title": e.get("summary", "(busy)"),
                    "start": datetime.fromisoformat(e["start"]["dateTime"]).astimezone(TZ),
                    "end": datetime.fromisoformat(e["end"]["dateTime"]).astimezone(TZ),
                    "updated": e.get("updated", "")})
    return out


# ---------- in-app calendar (the student edits; changes go straight to Google Calendar) ----------
def events_for_ui(start_iso, end_iso):
    svc = g.calendar()
    items = g.with_retry(lambda: svc.events().list(
        calendarId="primary", timeMin=start_iso, timeMax=end_iso, singleEvents=True,
        orderBy="startTime", maxResults=500).execute()).get("items", [])
    done = {r["event_id"]: r["done"] for r in db.query("SELECT event_id, done FROM sessions")}
    out = []
    for e in items:
        priv = e.get("extendedProperties", {}).get("private", {})
        ours = priv.get("studypilot") == "true"
        kind = priv.get("kind", "session") if ours else "mine"
        all_day = "date" in e.get("start", {})
        color = COLOR_HEX.get(e.get("colorId", ""), "#64748b" if kind == "mine" else "#3f51b5")
        out.append({
            "id": e["id"], "title": e.get("summary", "(busy)"), "kind": kind,
            "start": e["start"].get("dateTime") or e["start"].get("date"),
            "end": e["end"].get("dateTime") or e["end"].get("date"),
            "allDay": all_day, "color": color, "assessment_id": priv.get("assessment_id"),
            "recurring": bool(e.get("recurringEventId")),
            "done": bool(done.get(e["id"])),
            "editable": kind in ("session", "mine") and not all_day and not e.get("recurringEventId"),
        })
    return out


def _parse_local(iso):
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def add_student_event(title, start_iso, end_iso):
    """The student's own event (not tagged as StudyPilot) — e.g. 'Cricket match'."""
    svc = g.calendar()
    body = {"summary": title or "Busy",
            "start": {"dateTime": _parse_local(start_iso).isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": _parse_local(end_iso).isoformat(), "timeZone": TIMEZONE}}
    ev = _insert_once(svc, body)
    return {"id": ev["id"]}


def update_event_from_ui(event_id, start_iso, end_iso, title=""):
    svc = g.calendar()
    patch = {"start": {"dateTime": _parse_local(start_iso).isoformat(), "timeZone": TIMEZONE},
             "end": {"dateTime": _parse_local(end_iso).isoformat(), "timeZone": TIMEZONE}}
    if title:
        patch["summary"] = title
    g.with_retry(lambda: svc.events().patch(calendarId="primary", eventId=event_id, body=patch).execute())
    db.execute("UPDATE sessions SET start=?, end=? WHERE event_id=?",
               (_parse_local(start_iso).isoformat(), _parse_local(end_iso).isoformat(), event_id))
    return {"ok": True}


def delete_event_from_ui(event_id):
    svc = g.calendar()
    ev = g.with_retry(lambda: svc.events().get(calendarId="primary", eventId=event_id).execute())
    kind = ev.get("extendedProperties", {}).get("private", {}).get("kind", "session")
    if _is_ours(ev) and kind != "session":
        raise PermissionError("Deadline markers and timetable blocks are managed by StudyPilot.")
    g.with_retry(lambda: svc.events().delete(calendarId="primary", eventId=event_id).execute())
    db.execute("DELETE FROM sessions WHERE event_id=?", (event_id,))
    return {"ok": True}


def find_free_slot(minutes, after: datetime, before: datetime, prefer_evening=True):
    """First free slot of `minutes` inside the study window between after and before."""
    need = timedelta(minutes=minutes)
    for s, e in get_free_slots(after, before):
        start = s
        if prefer_evening:
            from agents import coach
            evening = s.replace(hour=coach.preferred_hour(17), minute=0, second=0, microsecond=0)
            if s < evening and evening + need <= e:
                start = evening
        start = start + timedelta(minutes=(30 - start.minute % 30) % 30)
        start = start.replace(second=0, microsecond=0)
        if start + need <= e:
            return start, start + need
    return None


def _is_ours(ev):
    return ev.get("extendedProperties", {}).get("private", {}).get("studypilot") == "true"


def delete_study_event(event_id):
    svc = g.calendar()
    ev = g.with_retry(lambda: svc.events().get(calendarId="primary", eventId=event_id).execute())
    if not _is_ours(ev):
        raise PermissionError("Refusing to delete an event StudyPilot did not create.")
    g.with_retry(lambda: svc.events().delete(calendarId="primary", eventId=event_id).execute())
    db.execute("DELETE FROM sessions WHERE event_id=?", (event_id,))


def move_study_event(event_id, new_start: datetime):
    svc = g.calendar()
    ev = g.with_retry(lambda: svc.events().get(calendarId="primary", eventId=event_id).execute())
    if not _is_ours(ev):
        raise PermissionError("Refusing to move an event StudyPilot did not create.")
    old_s = datetime.fromisoformat(ev["start"]["dateTime"])
    old_e = datetime.fromisoformat(ev["end"]["dateTime"])
    new_end = new_start + (old_e - old_s)
    patch = {"start": {"dateTime": new_start.isoformat(), "timeZone": TIMEZONE},
             "end": {"dateTime": new_end.isoformat(), "timeZone": TIMEZONE}}
    g.with_retry(lambda: svc.events().patch(calendarId="primary", eventId=event_id,
                                            body=patch).execute())
    db.execute("UPDATE sessions SET start=?, end=? WHERE event_id=?",
               (new_start.isoformat(), new_end.isoformat(), event_id))
