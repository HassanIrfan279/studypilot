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

    free = []
    day = start.astimezone(TZ).date()
    while day <= end.astimezone(TZ).date():
        w_start = datetime.combine(day, _hm(STUDY_WINDOW_START), TZ)
        w_end = datetime.combine(day, _hm(STUDY_WINDOW_END), TZ)
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


def create_study_event(item, course_name, start, end, idx, total):
    svc = g.calendar()
    title = f"📘 {course_name} — {item['title']} prep (Session {idx}/{total})"
    body = {
        "summary": title,
        "description": f"StudyPilot study session.\nPrep pack: {FRONTEND_URL}/prep/{item['id']}\n"
                       f"Classroom: {item.get('link', '')}",
        "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
        "colorId": course_color(item["course_id"]),
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]},
        "extendedProperties": {"private": {"studypilot": "true", "assessment_id": item["id"]}},
    }
    ev = g.with_retry(lambda: svc.events().insert(calendarId="primary", body=body).execute())
    db.execute("INSERT OR REPLACE INTO sessions(event_id, assessment_id, title, start, end, done) "
               "VALUES (?,?,?,?,?,0)", (ev["id"], item["id"], title, start.isoformat(),
                                        end.isoformat()))
    return ev


def list_studypilot_events(assessment_id=None, future_only=True):
    svc = g.calendar()
    props = ["studypilot=true"] + ([f"assessment_id={assessment_id}"] if assessment_id else [])
    kwargs = {"calendarId": "primary", "privateExtendedProperty": props, "singleEvents": True,
              "orderBy": "startTime", "maxResults": 250}
    if future_only:
        kwargs["timeMin"] = datetime.now(timezone.utc).isoformat()
    return g.with_retry(lambda: svc.events().list(**kwargs).execute()).get("items", [])


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
