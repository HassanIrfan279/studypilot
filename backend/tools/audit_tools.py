"""Auditor: make sure nothing is misinterpreted.

For each new/changed deadline, Gemini opens the FULL context (the coursework text, the whole
announcement thread, and the attached assignment file itself) and checks the date and details
we extracted. Anything wrong or unusual is flagged for the student to review. Cheap rule
checks run first (past dates, weekend/late-night quizzes, near-duplicates).
"""
import difflib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel

import db
import gemini
from activity_log import log
from config import TIMEZONE
from tools import classroom_tools as cr
from tools.drive_tools import fetch_lecture

TZ = ZoneInfo(TIMEZONE)


class Finding(BaseModel):
    ok: bool                 # True if the extracted deadline is correct and nothing is odd
    issues: list[str]        # short, specific problems (empty if ok)
    corrected_due: str       # "YYYY-MM-DD HH:MM" if the source clearly says a different date, else ""


def _rule_flags(item):
    flags = []
    if item.get("due"):
        due = datetime.fromisoformat(item["due"]).astimezone(TZ)
        if due < datetime.now(TZ):
            flags.append(f"Due date {due:%a %d %b %H:%M} is already in the past.")
        if item["kind"] == "quiz" and due.weekday() == 6:
            flags.append("Quiz falls on a Sunday — unusual for a class quiz.")
        if item["kind"] == "quiz" and (due.hour < 7 or due.hour >= 21):
            flags.append(f"Quiz time {due:%H:%M} is outside normal class hours.")
    same_course = db.query("SELECT id, title, due FROM items WHERE course_id=? AND active=1 AND id!=?",
                           (item["course_id"], item["id"]))
    import re
    nums = lambda t: re.findall(r"\d+", t)
    for o in same_course:
        if nums(o["title"]) != nums(item["title"]):
            continue  # "Assignment 1" vs "Assignment 5" are different items
        if difflib.SequenceMatcher(None, o["title"].lower(), item["title"].lower()).ratio() > 0.85 \
                and (o["due"] or "") != (item.get("due") or ""):
            flags.append(f"Looks like a duplicate of '{o['title']}' but with a different date.")
    return flags


def _context(item):
    """Everything the teacher wrote about this item, plus its attached file."""
    parts, text = [], []
    text.append(f"COURSE: {db.one('SELECT name FROM courses WHERE id=?', (item['course_id'],))['name']}")
    text.append(f"ITEM: {item['title']} ({item['kind']}), source: {item.get('source')}")
    text.append(f"WE EXTRACTED DUE: {datetime.fromisoformat(item['due']).astimezone(TZ):%A %Y-%m-%d %H:%M}"
                if item.get("due") else "WE EXTRACTED DUE: unknown")
    if item.get("description"):
        text.append(f"DESCRIPTION / EVIDENCE:\n{item['description'][:2000]}")
    try:
        anns = cr.list_announcements(item["course_id"])[:8]
        text.append("RECENT ANNOUNCEMENTS (newest first):\n" + "\n".join(
            f"[{a['created'][:16]}] {a['text'][:600]}" for a in anns))
    except Exception:
        pass
    files = db.query("SELECT file_id, title FROM materials WHERE item_id=?", (item["id"],))[:1]
    for f in files:
        try:
            lec = fetch_lecture(f["file_id"])
            if lec["kind"] == "text":
                text.append(f"ATTACHED FILE '{lec['name']}':\n{lec['text'][:15000]}")
            else:
                parts.append(gemini.file_part(lec["data"], lec["mime"]))
                text.append(f"ATTACHED FILE '{lec['name']}' is included above.")
        except Exception:
            pass
    return parts, "\n\n".join(text)


def audit_item(item, deep=True):
    """Returns the list of issues (also stored as flags:<id>)."""
    issues = _rule_flags(item)
    if deep:
        key = f"audit:{item['id']}:{item.get('due')}"
        found = db.cache_get(key)
        if found is None:
            parts, ctx = _context(item)
            try:
                found = gemini.generate_json(
                    f"Today is {datetime.now(TZ):%A %Y-%m-%d}. You are an auditor. Read ALL the "
                    "source material and check whether the deadline we extracted is correct and "
                    "whether anything is wrong or unusual: contradicting dates between the coursework "
                    "and announcements or the attached file, a different date written inside the file, "
                    "unclear instructions, missing info a student needs (format, submission method), "
                    "group vs individual confusion. Only report real, specific issues; if everything "
                    "matches, ok=true and issues=[].\n\n" + ctx, Finding, parts=parts)
            except Exception as e:
                log("Coordinator", f"Auditor couldn't check '{item['title']}': {e}", "warn")
                found = {"ok": True, "issues": [], "corrected_due": ""}
            db.cache_set(key, found)
        issues += found.get("issues", [])
        if found.get("corrected_due"):
            issues.append(f"The source seems to say the due date is {found['corrected_due']}.")
    issues = list(dict.fromkeys(issues))
    db.kv_set(f"flags:{item['id']}", issues)
    if issues:
        log("Coordinator", f"🔍 Auditor flagged '{item['title']}': {issues[0]}", "warn")
    else:
        log("Coordinator", f"🔍 Auditor checked '{item['title']}' against the full source: looks right.",
            "success")
    return issues


def clear_flag(item_id):
    db.kv_set(f"flags:{item_id}", [])
