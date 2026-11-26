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
    # Deadlines we already track from this course's announcements
    tracked_rows = db.query("SELECT * FROM items WHERE course_id=? AND source='announcement' "
                            "AND active=1", (c["id"],))
    tracked = {r["title"].lower(): r for r in tracked_rows}
    recent = [a for a in anns if _recent(a["created"] or a["update_time"])]
    found, ok = [], True
    if recent:
        try:
            found = st.extract_course_deadlines(
                c["name"], recent,
                [{"title": r["title"], "kind": r["kind"], "due": _local(r["due"])} for r in tracked_rows])
        except Exception as e:
            ok = False
            log("Sync", f"Couldn't read {c['name']} announcements with Gemini — keeping the "
                        f"deadlines I already know ({type(e).__name__}).", "warn")

    seen, new_titles = set(), []
    for d in found:
        prev = tracked.get(d["title"].lower())
        if d.get("status") == "cancelled":
            if prev:
                seen.add(prev["id"])  # tracked + clearly cancelled -> let it be removed
                db.kv_set(f"cancel_reason:{prev['id']}", d.get("evidence", ""))
            continue
        item_id = prev["id"] if prev else f"ann-{c['id']}-{_slug(d['title'])}"
        if not prev:
            new_titles.append(d["title"])
        items.append({"id": item_id, "course_id": c["id"], "title": prev["title"] if prev else d["title"],
                      "description": d.get("evidence") or "Found in a class announcement",
                      "kind": "quiz" if d["kind"] == "quiz" or cr.QUIZ_WORDS.search(d["title"])
                      else "assignment",
                      "due": _hidden_due(d), "update_time": recent[-1]["update_time"] if recent else "",
                      "link": recent[0]["link"] if recent else "", "files": [],
                      "source": "announcement"})
        seen.add(item_id)
    # Safety net: never drop a tracked deadline unless an announcement clearly cancelled it
    for r in tracked_rows:
        if r["id"] not in seen or not ok:
            if any(i["id"] == r["id"] for i in items):
                continue
            items.append({**r, "files": []})
    if new_titles:
        log("Sync", f"🔎 Gemini found {len(new_titles)} deadline(s) hidden in {c['name']} "
                    f"announcements: {', '.join(new_titles)}.")
    return items, materials


def _local(iso):
    if not iso:
        return None
    return datetime.fromisoformat(iso).astimezone(ZoneInfo(TIMEZONE)).strftime("%a %Y-%m-%d %H:%M")


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
