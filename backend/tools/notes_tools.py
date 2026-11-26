"""Study notes + the student's StudyPilot Drive folder.

Notes are detailed, easy-format Markdown per deadline (idea -> intuition -> worked example ->
common mistakes -> quick check). The student can edit them by hand or ask Gemini to edit them,
and the agent rewrites them after a weak quiz. Every version is mirrored to Google Drive as a
Google Doc inside StudyPilot/<Subject>/<Topic>/ next to shortcuts to the lecture files, and can
be downloaded as a PDF.

Drive access uses the drive.file scope for writing: StudyPilot only ever touches files and
folders it created itself.
"""
import io
import json
import re
import threading
import time

import markdown as md_lib
from googleapiclient.http import MediaIoBaseUpload

import db
import gemini
import google_clients as g
from activity_log import log, refresh
from tools import study_tools as st
from tools.drive_tools import fetch_lecture

FOLDER = "application/vnd.google-apps.folder"
DOC = "application/vnd.google-apps.document"
SHORTCUT = "application/vnd.google-apps.shortcut"
_drive_lock = threading.Lock()

db.execute("CREATE TABLE IF NOT EXISTS notes (assessment_id TEXT PRIMARY KEY, md TEXT, "
           "version INTEGER, updated REAL, history TEXT, doc_id TEXT, doc_link TEXT, "
           "folder_link TEXT, reason TEXT)")

NOTES_SYSTEM = (
    "You are StudyPilot's strict but caring teacher writing study notes for a Pakistani university "
    "CS student. Write in clear, simple English with short sentences. Stay grounded in the lecture "
    "material; if you add a standard textbook fact the lecture doesn't state, keep it minimal and "
    "correct. Use Markdown only: headings, bullet lists, bold, tables, and fenced code blocks for "
    "code or pseudo-code. NO LaTeX or $...$ math: write math as plain text with Unicode "
    "(e.g. G = (V, E), O(n²), Σ, ≤). Never write the student's graded assignment for them.")

FORMAT = """Format (Markdown):
# <title> — Study notes
> One line: what this covers and how long to study it.

## Contents
(bullet list of the topics)

Then for EACH important topic:
## <n>. <Topic name>
**The big idea:** 2-3 sentences.
**Intuition:** an everyday analogy a struggling student gets instantly.
**How it works:** the steps / rules / formula, as a short list or table.
**Worked example:** a complete step-by-step example with real numbers or a small input.
**Common mistakes:** 2-4 bullets of what students get wrong.
**Quick check:** 2 short questions, each followed by *Answer:* on its own line.

End with:
## Exam cheat sheet
(the 8-12 must-remember facts, one line each)"""


# ---------- storage ----------
def get_notes(assessment_id):
    row = db.one("SELECT * FROM notes WHERE assessment_id=?", (assessment_id,))
    if not row:
        return None
    row["history"] = json.loads(row["history"] or "[]")
    row["versions"] = len(row["history"])
    return row


def _save(assessment_id, text, reason):
    prev = get_notes(assessment_id)
    history = (prev["history"] if prev else [])
    if prev:
        history = (history + [{"md": prev["md"], "reason": prev["reason"], "ts": prev["updated"]}])[-8:]
    version = (prev["version"] + 1) if prev else 1
    db.execute("INSERT OR REPLACE INTO notes(assessment_id, md, version, updated, history, doc_id, "
               "doc_link, folder_link, reason) VALUES (?,?,?,?,?,?,?,?,?)",
               (assessment_id, text, version, time.time(), json.dumps(history),
                prev and prev["doc_id"], prev and prev["doc_link"], prev and prev["folder_link"],
                reason))
    refresh()
    # Mirror to Drive in the background so the UI never waits on it
    threading.Thread(target=_sync_quietly, args=(assessment_id,), daemon=True).start()
    return get_notes(assessment_id)


def _clean(text):
    text = text.strip()
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", text, re.S)
    return (m.group(1) if m else text).strip()


# ---------- generate / edit ----------
def _lecture_parts(assessment_id, limit=3):
    """The real lecture files (not just summaries) so the notes are detailed."""
    parts, names = [], []
    for fid in st.lectures_for_assessment(assessment_id, limit=limit):
        try:
            lec = fetch_lecture(fid)
        except Exception as e:
            log("Tutor", f"Couldn't open a lecture file for notes: {e}", "warn")
            continue
        names.append(lec["name"])
        if lec["kind"] == "text":
            parts.append(f"LECTURE '{lec['name']}':\n{lec['text'][:50000]}")
        else:
            parts.append(gemini.file_part(lec["data"], lec["mime"]))
    return parts, names


def generate_notes(assessment_id, refresh_notes=False):
    existing = get_notes(assessment_id)
    if existing and not refresh_notes:
        return existing
    item = st.get_item(assessment_id)
    if not item:
        return None
    parts, names = _lecture_parts(assessment_id)
    if not parts:
        analyses = st._analyses(st.lectures_for_assessment(assessment_id))
        if not analyses:
            raise ValueError("No lecture files found for this deadline yet.")
        parts = [st._material_text(analyses)]
    log("Tutor", f"✍️ Writing detailed study notes for '{item['title']}' from "
                 f"{len(names) or 'the'} lecture file(s)…")
    weak = _weak_topics(assessment_id)
    weak_txt = ("\nThe student is weak on these (from their quiz mistakes) — explain them extra "
                "carefully and start with a '## ⚠️ Your weak spots' section:\n"
                + "\n".join(f"- {w}" for w in weak)) if weak else ""
    text = _clean(gemini.generate_text(
        f"Write complete study notes for '{item['title']}' ({st.course_name(item['course_id'])}). "
        f"Cover every topic in the attached lecture material that could be tested.{weak_txt}\n\n{FORMAT}",
        parts=parts, system=NOTES_SYSTEM))
    notes = _save(assessment_id, text, "Written from your lectures")
    log("Tutor", f"📓 Study notes ready for '{item['title']}' ({len(text.split())} words).", "success")
    return notes


def edit_notes(assessment_id, instruction, reason=None):
    """Gemini edits the notes the way the student asked ('simpler', 'add an example', ...)."""
    notes = get_notes(assessment_id)
    if not notes:
        return None
    log("Tutor", f"Editing study notes: “{instruction[:80]}”")
    text = _clean(gemini.generate_text(
        f"Here are a student's study notes in Markdown. Apply this change: {instruction}\n"
        "Keep everything else (structure, headings, other topics) unless the change needs it. "
        "Return the COMPLETE updated notes in Markdown only, no commentary.\n\n"
        f"NOTES:\n{notes['md']}", system=NOTES_SYSTEM))
    if len(text) < 0.3 * len(notes["md"]):
        raise ValueError("The edit came back incomplete, so I kept your notes as they were.")
    return _save(assessment_id, text, reason or f"AI edit: {instruction[:80]}")


def save_manual(assessment_id, text):
    return _save(assessment_id, text, "Edited by you")


def undo(assessment_id):
    notes = get_notes(assessment_id)
    if not notes or not notes["history"]:
        return notes
    last = notes["history"][-1]
    db.execute("UPDATE notes SET md=?, reason=?, history=?, version=version+1, updated=? "
               "WHERE assessment_id=?",
               (last["md"], "Restored previous version", json.dumps(notes["history"][:-1]),
                time.time(), assessment_id))
    threading.Thread(target=_sync_quietly, args=(assessment_id,), daemon=True).start()
    refresh()
    return get_notes(assessment_id)


def _weak_topics(assessment_id):
    wrong = []
    for r in db.query("SELECT wrong FROM quiz_results WHERE assessment_id=? AND score<0.6 "
                      "ORDER BY id DESC LIMIT 3", (assessment_id,)):
        try:
            wrong += json.loads(r["wrong"] or "[]")
        except ValueError:
            pass
    return list(dict.fromkeys(wrong))[:8]


def revise_for_weak(assessment_id, wrong):
    """After a weak quiz: rewrite the notes around exactly what the student got wrong."""
    if not get_notes(assessment_id) or not wrong:
        return None
    items = "\n".join(f"- {w}" for w in wrong[:8])
    try:
        notes = edit_notes(
            assessment_id,
            "The student just failed a practice quiz. They got these questions wrong:\n" + items +
            "\nAdd (or replace) a section right after the title called '## ⚠️ Your weak spots' that "
            "re-teaches each of these concepts more simply, with a NEW worked example for each and "
            "the exact mistake to avoid. Also make the matching topic sections clearer.",
            reason="Rewritten after your weak quiz")
        log("Tutor", "📓 Rewrote the study notes around your quiz mistakes.", "success")
        return notes
    except Exception as e:
        log("Tutor", f"Couldn't rewrite notes after the quiz: {e}", "warn")
        return None


# ---------- Google Drive: StudyPilot/<Subject>/<Topic>/ ----------
def _q(s):
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _folder(name, parent=None):
    """Find-or-create a folder StudyPilot made (drive.file can only see those)."""
    key = f"folder:{parent or 'root'}:{name}"
    fid = db.kv_get(key)
    svc = g.drive()
    if fid:
        try:
            f = svc.files().get(fileId=fid, fields="id,trashed").execute()
            if not f.get("trashed"):
                return fid
        except Exception:
            pass
    q = f"name='{_q(name)}' and mimeType='{FOLDER}' and trashed=false"
    if parent:
        q += f" and '{parent}' in parents"
    found = g.with_retry(lambda: svc.files().list(q=q, fields="files(id)", pageSize=1).execute())
    if found.get("files"):
        fid = found["files"][0]["id"]
    else:
        body = {"name": name, "mimeType": FOLDER}
        if parent:
            body["parents"] = [parent]
        fid = g.with_retry(lambda: svc.files().create(body=body, fields="id").execute())["id"]
    db.kv_set(key, fid)
    return fid


def _shortcut(target_id, name, parent):
    key = f"shortcut:{parent}:{target_id}"
    if db.kv_get(key):
        return
    svc = g.drive()
    try:
        g.with_retry(lambda: svc.files().create(body={
            "name": name, "mimeType": SHORTCUT, "parents": [parent],
            "shortcutDetails": {"targetId": target_id}}, fields="id").execute())
        db.kv_set(key, True)
    except Exception as e:
        log("Drive", f"Couldn't add a shortcut to '{name}': {e}", "warn")


def _html(md_text, title):
    body = md_lib.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    return (f"<html><head><meta charset='utf-8'><title>{title}</title><style>"
            "body{font-family:Arial;font-size:11pt;line-height:1.45} h1{color:#3730a3} "
            "h2{color:#1e293b;border-bottom:1px solid #cbd5e1} table{border-collapse:collapse} "
            "td,th{border:1px solid #94a3b8;padding:4px 8px} pre,code{font-family:Consolas;"
            "background:#f1f5f9} blockquote{color:#475569;border-left:4px solid #6366f1;padding-left:8px}"
            f"</style></head><body>{body}</body></html>")


def topic_folder(assessment_id):
    item = st.get_item(assessment_id)
    root = _folder("StudyPilot")
    subject = _folder(st.course_name(item["course_id"]).strip() or "Course", root)
    return _folder(re.sub(r"[\\/]", "-", item["title"]).strip()[:80], subject), item


def sync_to_drive(assessment_id):
    """Put the notes (as a Google Doc) + shortcuts to the lectures in the topic folder."""
    notes = get_notes(assessment_id)
    with _drive_lock:
        folder, item = topic_folder(assessment_id)
        for fid in st.lectures_for_assessment(assessment_id, limit=4):
            m = db.one("SELECT title FROM materials WHERE file_id=?", (fid,))
            _shortcut(fid, (m and m["title"]) or "Lecture", folder)
        if not notes:
            return None
        svc = g.drive()
        title = f"{item['title']} — Study notes"
        media = MediaIoBaseUpload(io.BytesIO(_html(notes["md"], title).encode("utf-8")),
                                  mimetype="text/html", resumable=False)
        doc = None
        if notes["doc_id"]:
            try:
                doc = g.with_retry(lambda: svc.files().update(
                    fileId=notes["doc_id"], body={"name": title}, media_body=media,
                    fields="id,webViewLink").execute())
            except Exception:
                doc = None  # deleted by the student -> make a new one
                media = MediaIoBaseUpload(io.BytesIO(_html(notes["md"], title).encode("utf-8")),
                                          mimetype="text/html", resumable=False)
        if not doc:
            doc = g.with_retry(lambda: svc.files().create(
                body={"name": title, "mimeType": DOC, "parents": [folder]}, media_body=media,
                fields="id,webViewLink").execute())
        folder_link = f"https://drive.google.com/drive/folders/{folder}"
        db.execute("UPDATE notes SET doc_id=?, doc_link=?, folder_link=? WHERE assessment_id=?",
                   (doc["id"], doc.get("webViewLink"), folder_link, assessment_id))
    log("Drive", f"📁 Saved notes to Drive: StudyPilot / {st.course_name(item['course_id'])} / "
                 f"{item['title']}", "success")
    refresh()
    return doc


def _sync_quietly(assessment_id):
    try:
        sync_to_drive(assessment_id)
    except Exception as e:
        log("Drive", f"Drive sync for notes failed (will retry next edit): {e}", "warn")


def organize_drive(upcoming):
    """Build the whole StudyPilot/<Subject>/<Topic>/ tree for the upcoming deadlines."""
    done = 0
    for it in upcoming:
        try:
            sync_to_drive(it["id"])
            done += 1
        except Exception as e:
            log("Drive", f"Couldn't organize '{it['title']}' in Drive: {e}", "warn")
            if "403" in str(e) or "insufficient" in str(e).lower():
                break
    if done:
        log("Drive", f"📁 Drive organized: StudyPilot folder with {done} topic folder(s), "
                     "lecture shortcuts and notes.", "success")


def notes_pdf(assessment_id):
    """PDF bytes via Google Docs export (same look as the Drive copy)."""
    notes = get_notes(assessment_id)
    if not notes:
        return None
    sync_to_drive(assessment_id)  # make sure the Doc has the latest edits
    notes = get_notes(assessment_id)
    svc = g.drive()
    return g.with_retry(lambda: svc.files().export(fileId=notes["doc_id"],
                                                   mimeType="application/pdf").execute())
