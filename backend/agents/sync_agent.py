"""Sync agent: pulls Classroom, saves a snapshot in SQLite, and detects what changed."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import db
from activity_log import log
from config import TIMEZONE
from tools import classroom_tools as cr
from tools import study_tools as st

RECENT_DAYS = 21  # only announcements from the last 3 weeks can contain live deadlines


def _hidden_due(d):
    """Turn Gemini's YYYY-MM-DD + HH:MM into an ISO UTC string (None if unknown)."""
    if not d["due_date"] or d["ambiguous"]:
        return None
    try:
        t = (d["due_time"] or "23:59")[:5]
        local = datetime.fromisoformat(f"{d['due_date']}T{t}").replace(tzinfo=ZoneInfo(TIMEZONE))
        return local.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def _recent(iso, days=RECENT_DAYS):
    if not iso:
        return False
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) > datetime.now(timezone.utc) - timedelta(days=days)


def _fetch_course(c):
    """Everything for one course (runs in parallel with other courses)."""
    items, materials = [], []
    work = cr.list_coursework(c["id"])
    mats = cr.list_materials(c["id"])
    anns = cr.list_announcements(c["id"])
    for w in work:
        items.append(w)
        for f in w["files"]:
            materials.append({**f, "course_id": c["id"], "item_id": w["id"], "created": w["update_time"]})
    for m in mats:
        for f in m["files"]:
            materials.append({**f, "course_id": c["id"], "item_id": None, "created": m["update_time"]})
    for a in anns:
        for f in a["files"]:
            materials.append({**f, "course_id": c["id"], "item_id": None, "created": a["update_time"]})

    # Hidden deadlines: one Gemini call per course, reading recent announcements in order
    recent = [a for a in anns if _recent(a["created"] or a["update_time"])]
    if recent:
        try:
            found = st.extract_course_deadlines(c["name"], recent)
        except Exception as e:
            log("Sync", f"Couldn't read {c['name']} announcements with Gemini: {e}", "warn")
            found = []
        for d in found:
            items.append({"id": f"ann-{c['id']}-{_slug(d['title'])}", "course_id": c["id"],
                          "title": d["title"], "description": "Found in a class announcement",
                          "kind": "quiz" if d["kind"] == "quiz" or cr.QUIZ_WORDS.search(d["title"])
                          else "assignment",
                          "due": _hidden_due(d), "update_time": recent[0]["update_time"],
                          "link": recent[0]["link"], "files": [], "source": "announcement"})
        known = {r["id"] for r in db.query("SELECT id FROM items WHERE course_id=? AND "
                                           "source='announcement'", (c["id"],))}
        if any(f"ann-{c['id']}-{_slug(d['title'])}" not in known for d in found):
            log("Sync", f"🔎 Gemini found {len(found)} deadline(s) hidden in {c['name']} "
                        f"announcements: {', '.join(d['title'] for d in found)}.")
    return items, materials


def fetch_all():
    """Read everything from Classroom. Returns (courses, items, materials)."""
    courses = cr.list_courses()
    items, materials = [], []
    with ThreadPoolExecutor(max_workers=5) as pool:
        for its, mats in pool.map(_fetch_course, courses):
            items.extend(its)
            materials.extend(mats)
    return courses, items, materials


def run_sync():
    """Returns a list of change dicts: {type: added|removed|due_changed|new_material, ...}."""
    courses, items, materials = fetch_all()
    first_run = not db.kv_get("synced_once")

    for idx, c in enumerate(courses):
        existing = db.one("SELECT color FROM courses WHERE id=?", (c["id"],))
        color = existing["color"] if existing else idx
        db.execute("INSERT OR REPLACE INTO courses(id, name, section, color) VALUES (?,?,?,?)",
                   (c["id"], c["name"], c["section"], color))

    changes = []
    old = {r["id"]: r for r in db.query("SELECT * FROM items WHERE active=1")}
    new_ids = set()
    for it in items:
        override = db.kv_get(f"due_override:{it['id']}")
        if override and not it["due"]:
            it["due"] = override
        new_ids.add(it["id"])
        prev = old.get(it["id"])
        if prev is None:
            changes.append({"type": "added", "item": it})
        elif (prev["due"] or "") != (it["due"] or ""):
            changes.append({"type": "due_changed", "item": it, "old_due": prev["due"]})
        db.execute("INSERT OR REPLACE INTO items(id, course_id, kind, title, description, due, "
                   "update_time, link, source, active) VALUES (?,?,?,?,?,?,?,?,?,1)",
                   (it["id"], it["course_id"], it["kind"], it["title"], it["description"],
                    it["due"], it["update_time"], it["link"], it.get("source", "classroom")))
    for item_id, prev in old.items():
        if item_id not in new_ids:
            db.execute("UPDATE items SET active=0 WHERE id=?", (item_id,))
            changes.append({"type": "removed", "item": prev})

    known = {r["file_id"] for r in db.query("SELECT file_id FROM materials")}
    for m in materials:
        if m["file_id"] not in known:
            known.add(m["file_id"])
            changes.append({"type": "new_material", "material": m})
        db.execute("INSERT OR REPLACE INTO materials(file_id, course_id, title, mime, link, item_id, "
                   "created) VALUES (?,?,?,?,?,COALESCE(?, (SELECT item_id FROM materials "
                   "WHERE file_id=?)),?)",
                   (m["file_id"], m["course_id"], m["title"], "", m["link"], m["item_id"],
                    m["file_id"], m["created"]))

    db.kv_set("synced_once", True)
    db.kv_set("last_sync", datetime.now(ZoneInfo(TIMEZONE)).isoformat())
    return {"first_run": first_run, "changes": changes, "courses": len(courses),
            "items": len(items), "materials": len(materials)}
