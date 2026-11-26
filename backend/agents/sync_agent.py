"""Sync agent: pulls Classroom, saves a snapshot in SQLite, and detects what changed."""
from datetime import datetime
from zoneinfo import ZoneInfo

import db
from activity_log import log
from config import TIMEZONE
from tools import classroom_tools as cr
from tools import study_tools as st


def _hidden_due(d):
    """Turn Gemini's YYYY-MM-DD + HH:MM into an ISO UTC string (None if unknown)."""
    if not d["due_date"] or d["ambiguous"]:
        return None
    try:
        t = d["due_time"] or "23:59"
        local = datetime.fromisoformat(f"{d['due_date']}T{t}").replace(tzinfo=ZoneInfo(TIMEZONE))
        return local.astimezone(ZoneInfo("UTC")).isoformat()
    except ValueError:
        return None


def fetch_all():
    """Read everything from Classroom. Returns (courses, items, materials)."""
    courses = cr.list_courses()
    items, materials = [], []
    for c in courses:
        for w in cr.list_coursework(c["id"]):
            items.append(w)
            for f in w["files"]:
                materials.append({**f, "course_id": c["id"], "item_id": w["id"],
                                  "created": w["update_time"]})
        for m in cr.list_materials(c["id"]):
            for f in m["files"]:
                materials.append({**f, "course_id": c["id"], "item_id": None,
                                  "created": m["update_time"]})
        for a in cr.list_announcements(c["id"]):
            for f in a["files"]:
                materials.append({**f, "course_id": c["id"], "item_id": None,
                                  "created": a["update_time"]})
            # Hidden deadlines written in plain text ("submit by next Monday")
            try:
                found = st.extract_hidden_deadlines(a["text"], a["created"] or a["update_time"])
            except Exception as e:
                log("Sync", f"Couldn't read an announcement with Gemini: {e}", "warn")
                found = []
            for i, d in enumerate(found):
                items.append({"id": f"ann-{a['id']}-{i}", "course_id": c["id"], "title": d["title"],
                              "description": a["text"][:500], "kind": d["kind"] or "assignment",
                              "due": _hidden_due(d), "update_time": a["update_time"],
                              "link": a["link"], "files": [], "source": "announcement"})
    return courses, items, materials


def run_sync():
    """Returns a list of change dicts: {type: added|removed|due_changed|new_material, ...}."""
    courses, items, materials = fetch_all()
    first_run = db.one("SELECT COUNT(*) n FROM items")["n"] == 0 and not db.kv_get("synced_once")

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
