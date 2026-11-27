"""Sync agent: pulls Classroom, saves a snapshot in SQLite, and detects what changed."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import db
from activity_log import log
from config import TIMEZONE
from tools import classroom_tools as cr
from tools import gmail_tools as gm
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
    texts = [_norm(a["text"]) for a in anns]
    for d in found:
        prev = tracked.get(d["title"].lower())
        if d.get("status") == "cancelled":
            if prev:
                seen.add(prev["id"])  # tracked + clearly cancelled -> let it be removed
                db.kv_set(f"cancel_reason:{prev['id']}", d.get("evidence", ""))
            continue
        if not _still_posted({"title": d["title"], "description": d.get("evidence", "")}, texts):
            continue  # nothing in the current posts backs it up (deleted post, or Gemini echoed an old one)
        item_id = prev["id"] if prev else f"ann-{c['id']}-{_slug(d['title'])}"
        if item_id in seen:
            continue  # Gemini listed the same deadline twice
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
    # Safety net: never drop a tracked deadline just because Gemini skipped it once. Drop it only if
    # its source post is gone (the teacher deleted it): no current announcement holds its evidence
    # or its key words. Then the agents cancel it like any other removed deadline.
    for r in tracked_rows:
        if r["id"] not in seen or not ok:
            if any(i["id"] == r["id"] for i in items):
                continue
            if ok and r["id"] not in seen and not _still_posted(r, texts):
                db.kv_set(f"cancel_reason:{r['id']}", "The teacher deleted the announcement it came from.")
                log("Sync", f"🗑 '{r['title']}' in {c['name']}: its announcement was deleted, so it's no "
                            "longer a deadline.")
                continue
            items.append({**r, "files": []})
    if new_titles:
        log("Sync", f"🔎 Gemini found {len(new_titles)} deadline(s) hidden in {c['name']} "
                    f"announcements: {', '.join(new_titles)}.")
    return items, materials


_GENERIC = {"quiz", "test", "exam", "assignment", "the", "a", "an", "of", "on", "in", "for", "and", "class"}


def _norm(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").replace("\xa0", " ").lower()).split())


def _still_posted(row, texts):
    """Is a tracked announcement-deadline still backed by a current announcement?"""
    ev = row.get("description") or ""
    for frag in re.split(r"\.\.\.|…", ev):
        f = _norm(frag)
        if len(f) >= 12 and any(f in t for t in texts):
            return True
    keys = [w for w in _norm(row["title"]).split() if w not in _GENERIC]
    if not keys:
        return True  # nothing specific to look for: keep it to be safe
    return any(all(re.search(rf"\b{re.escape(k)}\b", t) for k in keys) for t in texts)


def _local(iso):
    if not iso:
        return None
    return datetime.fromisoformat(iso).astimezone(ZoneInfo(TIMEZONE)).strftime("%a %Y-%m-%d %H:%M")


def _email_items(courses):
    """Deadlines a teacher only sent by email (Gmail, read-only). Never drops a tracked one on error."""
    tracked_rows = db.query("SELECT * FROM items WHERE source='email' AND active=1")
    keep = [{**r, "files": []} for r in tracked_rows]
    if db.kv_get("gmail_disabled_until", 0) > datetime.now().timestamp():
        return keep
    by_name = {c["name"]: c for c in courses}
    names = {c["id"]: c["name"] for c in courses}
    try:
        emails = gm.recent_class_emails()
        found = gm.extract_email_deadlines(
            list(by_name), emails,
            [{"course": names.get(r["course_id"], ""), "title": r["title"], "kind": r["kind"],
              "due": _local(r["due"])} for r in tracked_rows],
            datetime.now(ZoneInfo(TIMEZONE)).strftime("%A %Y-%m-%d"),
            [f"[{names.get(r['course_id'], '')}] {r['title']}" for r in db.query(
                "SELECT course_id, title FROM items WHERE active=1 AND source!='email'")])
    except Exception as e:
        msg = str(e)
        if "403" in msg or "has not been used" in msg or "disabled" in msg:
            db.kv_set("gmail_disabled_until", datetime.now().timestamp() + 600)
            log("Sync", "Gmail isn't reachable (is the Gmail API enabled in Google Cloud?). "
                        "Retrying in 10 min.", "warn")
        else:
            log("Sync", f"Couldn't read class emails right now ({type(e).__name__}).", "warn")
        return keep
    tracked = {(r["course_id"], r["title"].lower()): r for r in tracked_rows}
    items, seen, new_titles = [], set(), []
    for d in found:
        c = by_name.get(d["course"])
        if not c:
            continue
        prev = tracked.get((c["id"], d["title"].lower()))
        if d.get("status") == "cancelled":
            if prev:
                seen.add(prev["id"])
                db.kv_set(f"cancel_reason:{prev['id']}", d.get("evidence", ""))
            continue
        item_id = prev["id"] if prev else f"mail-{c['id']}-{_slug(d['title'])}"
        if item_id in seen:
            continue
        if not prev:
            new_titles.append(f"{d['title']} ({c['name']})")
        items.append({"id": item_id, "course_id": c["id"], "title": prev["title"] if prev else d["title"],
                      "description": "📧 From email: " + (d.get("evidence") or ""),
                      "kind": "quiz" if d["kind"] == "quiz" or cr.QUIZ_WORDS.search(d["title"])
                      else "assignment",
                      "due": _hidden_due(d), "update_time": "", "link": "https://mail.google.com/",
                      "files": [], "source": "email"})
        seen.add(item_id)
    for r in tracked_rows:
        if r["id"] not in seen:
            items.append({**r, "files": []})
    if new_titles:
        log("Sync", f"📧 Gemini found {len(new_titles)} deadline(s) in your email: "
                    f"{', '.join(new_titles)}.")
    return items


def fetch_all():
    """Read everything from Classroom (+ class emails). Returns (courses, items, materials)."""
    courses = cr.list_courses()
    items, materials = [], []
    with ThreadPoolExecutor(max_workers=6) as pool:
        mail = pool.submit(_email_items, courses)
        for its, mats in pool.map(_fetch_course, courses):
            items.extend(its)
            materials.extend(mats)
        known = {i["id"] for i in items}
        items.extend(i for i in mail.result() if i["id"] not in known)
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
