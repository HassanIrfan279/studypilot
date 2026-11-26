"""Sync agent tools: read courses, coursework, announcements and materials from Google Classroom."""
import re
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

import google_clients as g
from config import TIMEZONE

QUIZ_WORDS = re.compile(r"\b(quiz|test|exam|midterm|mid-term|final|viva|sessional)\b", re.I)


def _all_pages(request_fn, key):
    """Classroom lists are paginated; collect every page."""
    out, token = [], None
    while True:
        resp = g.with_retry(lambda: request_fn(token).execute())
        out.extend(resp.get(key, []))
        token = resp.get("nextPageToken")
        if not token:
            return out


def due_to_iso(due_date, due_time):
    """Classroom gives dueDate/dueTime in UTC. Returns ISO string in UTC, or None."""
    if not due_date:
        return None
    if due_time:
        dt = datetime(due_date["year"], due_date["month"], due_date["day"],
                      due_time.get("hours", 0), due_time.get("minutes", 0), tzinfo=timezone.utc)
    else:  # date only -> end of that day, local time
        local = datetime.combine(datetime(due_date["year"], due_date["month"], due_date["day"]).date(),
                                 dtime(23, 59), tzinfo=ZoneInfo(TIMEZONE))
        dt = local.astimezone(timezone.utc)
    return dt.isoformat()


def extract_files(materials):
    """Pick out Drive files (lectures) from a Classroom 'materials' list."""
    files = []
    for m in materials or []:
        if "driveFile" in m:
            f = m["driveFile"]["driveFile"]
            files.append({"file_id": f["id"], "title": f.get("title", "Untitled"),
                          "link": f.get("alternateLink", "")})
    return files


def list_courses():
    svc = g.classroom()
    courses = _all_pages(lambda t: svc.courses().list(studentId="me", courseStates=["ACTIVE"],
                                                      pageToken=t), "courses")
    return [{"id": c["id"], "name": c["name"], "section": c.get("section", "")} for c in courses]


def list_coursework(course_id):
    svc = g.classroom()
    work = _all_pages(lambda t: svc.courses().courseWork().list(courseId=course_id, pageToken=t),
                      "courseWork")
    out = []
    for w in work:
        text = f"{w.get('title', '')} {w.get('description', '')}"
        out.append({
            "id": w["id"], "course_id": course_id, "title": w.get("title", "Untitled"),
            "description": w.get("description", ""),
            "kind": "quiz" if QUIZ_WORDS.search(text) else "assignment",
            "due": due_to_iso(w.get("dueDate"), w.get("dueTime")),
            "update_time": w.get("updateTime", ""), "link": w.get("alternateLink", ""),
            "files": extract_files(w.get("materials")),
        })
    return out


def list_announcements(course_id):
    svc = g.classroom()
    anns = _all_pages(lambda t: svc.courses().announcements().list(courseId=course_id, pageToken=t),
                      "announcements")
    return [{"id": a["id"], "course_id": course_id, "text": a.get("text", ""),
             "update_time": a.get("updateTime", ""), "link": a.get("alternateLink", ""),
             "created": a.get("creationTime", ""),
             "files": extract_files(a.get("materials"))} for a in anns]


def list_materials(course_id):
    svc = g.classroom()
    mats = _all_pages(lambda t: svc.courses().courseWorkMaterials().list(courseId=course_id,
                                                                          pageToken=t),
                      "courseWorkMaterial")
    return [{"id": m["id"], "course_id": course_id, "title": m.get("title", ""),
             "description": m.get("description", ""), "update_time": m.get("updateTime", ""),
             "files": extract_files(m.get("materials"))} for m in mats]
