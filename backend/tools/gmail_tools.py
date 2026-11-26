"""Reads the student's class emails (read-only) so deadlines a teacher only emailed aren't missed.

Classroom's own notification emails are skipped: we already read Classroom directly.
"""
import base64
import hashlib
import html
import re
from datetime import datetime

from pydantic import BaseModel

import db
import gemini
import google_clients as g
from activity_log import log

QUERY = ("newer_than:21d -from:classroom.google.com -category:promotions -category:social "
         "(quiz OR assignment OR deadline OR exam OR viva OR submission OR submit OR lab OR "
         "presentation OR postponed OR cancelled OR rescheduled OR midterm OR project)")


class EmailDeadline(BaseModel):
    course: str        # EXACT course name from the list, or "" if it isn't for any of them
    title: str
    kind: str          # "quiz" or "assignment"
    due_date: str      # YYYY-MM-DD or ""
    due_time: str      # HH:MM or ""
    ambiguous: bool
    status: str        # "active" or "cancelled"
    evidence: str      # short quote from the email


class EmailDeadlines(BaseModel):
    deadlines: list[EmailDeadline]


def gmail():
    return g._service("gmail", "v1")


def _text(payload):
    """Plain text of a message (prefers text/plain, falls back to stripped HTML)."""
    plain, rich = [], []

    def walk(p):
        mime = p.get("mimeType", "")
        data = p.get("body", {}).get("data")
        if data:
            raw = base64.urlsafe_b64decode(data + "===").decode("utf-8", "ignore")
            (plain if mime == "text/plain" else rich if mime == "text/html" else []).append(raw)
        for c in p.get("parts", []) or []:
            walk(c)

    walk(payload)
    if plain:
        return "\n".join(plain)
    text = re.sub(r"<(script|style).*?</\1>", " ", " ".join(rich), flags=re.S | re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", text))


def recent_class_emails(max_results=20):
    """[{id, from, subject, date, text}] — cached 2 minutes so syncs don't hammer Gmail."""
    cached = db.cache_get("gmail:recent", max_age=120)
    if cached is not None:
        return cached
    svc = gmail()
    ids = g.with_retry(lambda: svc.users().messages().list(
        userId="me", q=QUERY, maxResults=max_results).execute()).get("messages", [])
    out = []
    for m in ids:
        key = f"gmail:msg:{m['id']}"
        msg = db.cache_get(key)
        if msg is None:
            full = g.with_retry(lambda: svc.users().messages().get(
                userId="me", id=m["id"], format="full").execute())
            hdr = {h["name"].lower(): h["value"] for h in full["payload"].get("headers", [])}
            msg = {"id": m["id"], "from": hdr.get("from", ""), "subject": hdr.get("subject", ""),
                   "date": datetime.fromtimestamp(int(full["internalDate"]) / 1000).isoformat(),
                   "text": re.sub(r"\s+", " ", _text(full["payload"]))[:2000]}
            db.cache_set(key, msg)
        out.append(msg)
    out.sort(key=lambda e: e["date"])
    db.cache_set("gmail:recent", out)
    return out


def extract_email_deadlines(courses, emails, tracked, today, elsewhere=()):
    """One Gemini call over all recent class emails -> current deadlines per course."""
    if not emails:
        return []
    feed = "\n\n".join(f"[{e['date'][:16]}] From: {e['from']}\nSubject: {e['subject']}\n{e['text']}"
                       for e in emails)
    known = "\n".join(f"- [{t['course']}] {t['title']} ({t['kind']}), due {t['due'] or 'unknown'}"
                      for t in tracked) or "- none"
    names = "\n".join(f"- {c}" for c in courses)
    other = "\n".join(f"- {t}" for t in elsewhere) or "- none"
    key = "maildl:" + hashlib.sha1((names + feed + known + other).encode()).hexdigest()
    cached = db.cache_get(key)
    if cached is not None:
        return cached
    log("Sync", f"📧 Reading {len(emails)} recent class email(s) with Gemini…")
    out = gemini.generate_json(
        f"Today is {today}. Below are a university student's recent emails, oldest first, their "
        "courses, and deadlines we already track from email.\n"
        "Return every quiz / test / viva / exam / submission / presentation deadline the emails "
        "announce for these courses:\n"
        "1. course must be EXACTLY one of the course names below (match by subject name, code or "
        "teacher context). If an email isn't about one of these courses, skip it.\n"
        "2. Every already-tracked deadline must appear again with EXACTLY the same title, updated "
        "by later emails (postponed -> new date; vague new date -> ambiguous=true).\n"
        "3. status='cancelled' only if an email clearly cancels that specific item.\n"
        "4. SKIP deadlines that are already on Google Classroom (list below) — those are "
        "handled there.\n"
        "5. Ignore newsletters, ads, university-wide notices and anything not a course deadline.\n"
        "6. Resolve relative dates from the email's date. In-class quiz without a time -> 09:00. "
        "kind='quiz' for quiz/test/viva/exam, else 'assignment'. Short quote in evidence.\n\n"
        f"COURSES:\n{names}\n\nALREADY TRACKED FROM EMAIL:\n{known}\n\nALREADY ON CLASSROOM:\n{other}\n\nEMAILS:\n{feed}",
        EmailDeadlines)
    found = out["deadlines"]
    db.cache_set(key, found)
    return found
