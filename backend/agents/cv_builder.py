"""CV builder: the career agent interviews the student (one question at a time, skipping what it
already knows), then writes a clean, ATS-friendly CV itself.

The CV lives as a Google Doc in StudyPilot/Internships (the student can edit it there), is
exported to PDF, and becomes the CV the internship agent attaches to applications.
Honesty rule: it may phrase things strongly, but never invents a project, number, grade or role.
"""
import html
import io
import json
import time

from googleapiclient.http import MediaIoBaseUpload
from pydantic import BaseModel

import db
import gemini
import google_clients as g
from activity_log import log, refresh
from agents import career_agent as career

AGENT = "Career"
DOC = "application/vnd.google-apps.document"


class Link(BaseModel):
    label: str
    url: str


class Education(BaseModel):
    institution: str
    degree: str
    dates: str
    details: str              # CGPA, relevant courses, honours — only if given


class SkillGroup(BaseModel):
    label: str                # e.g. "Languages", "Frameworks", "Tools"
    items: list[str]


class Entry(BaseModel):
    title: str                # project name or role
    org: str                  # company/society, or tech stack for a project
    dates: str
    link: str
    bullets: list[str]


class CV(BaseModel):
    name: str
    headline: str             # e.g. "Computer Science student · Full-stack & ML"
    email: str
    phone: str
    city: str
    links: list[Link]
    summary: str              # 2 lines, specific
    education: list[Education]
    skills: list[SkillGroup]
    projects: list[Entry]
    experience: list[Entry]
    achievements: list[str]
    certifications: list[str]
    activities: list[str]


class Turn(BaseModel):
    done: bool
    message: str              # next question, or a short closing line
    cv: CV | None


SYSTEM = """You are StudyPilot's career coach building a university student's CV (Pakistan) by
interviewing them. Ask ONE short question at a time (max 2 sentences), react briefly to their
last answer, and dig for specifics that make a CV strong: what each project does, the tech used,
THEIR part, and real numbers (users, accuracy, speed, team size) — but if they don't know a
number, move on; never pressure them to make one up.
Cover, in a natural order (skip anything already known and confirm it in one line instead):
contact (phone, city, LinkedIn/GitHub/portfolio), degree, semester, graduation year, CGPA (optional),
relevant courses, 2-4 projects in depth, any work/TA/freelance/volunteer experience, skills,
achievements (hackathons, competitions, scholarships, dean's list), certifications, societies,
and the kind of internship they want. The student may answer 'skip'.
After about 10-14 questions, or once you have enough, or when told to finish now: set
done=true, give a one-line closing message, and fill the full CV.
CV writing rules: strong action-verb bullets (Built, Designed, Led, Reduced...), 1-3 bullets per
entry, each under 25 words; put numbers in ONLY if the student gave them; never invent
projects, employers, dates, grades or skills; leave fields "" or lists empty when unknown.
Dates: use ONLY dates/years the student actually said; otherwise dates="" (never guess a year).
Order skills by relevance to the internships they want."""


def _known():
    """Everything StudyPilot already knows, so the interview doesn't ask twice."""
    facts = {"career_profile": career.profile(), "answers": db.kv_get("career_answers") or {},
             "study_profile": {k: v for k, v in (db.kv_get("profile") or {}).items()
                               if k in ("name", "goals", "summary")},
             "courses": [r["name"] for r in db.query("SELECT name FROM courses")]}
    try:
        me = g.oauth2().userinfo().get().execute()
        facts["google_account"] = {"name": me.get("name"), "email": me.get("email")}
    except Exception:
        pass
    old = db.kv_get("cv_draft")
    if old:
        facts["previous_cv"] = old["cv"]
    return json.dumps(facts, ensure_ascii=False, default=str)[:7000]


def next_turn(messages: list[dict], finish: bool = False) -> dict:
    transcript = "\n".join(f"{'COACH' if m['role'] == 'agent' else 'STUDENT'}: {m['text']}"
                           for m in messages) or "(interview not started — greet them by name, say "\
                                                  "in one line what you already know, then ask the first question)"
    turn = gemini.generate_json(
        f"WHAT STUDYPILOT ALREADY KNOWS:\n{_known()}\n\nINTERVIEW SO FAR:\n{transcript}\n\n"
        + ("The student clicked 'Draft my CV now': set done=true and write the best CV from what you have."
           if finish else "Write your next turn."),
        Turn, system=SYSTEM)
    if turn["done"] and turn.get("cv"):
        draft = build(turn["cv"])
        turn["draft"] = draft
    return turn


# ---------------------------------------------------------------- render
def _e(s):
    return html.escape(str(s or ""))


def _entries(title, entries):
    if not entries:
        return ""
    out = [f"<h2>{title}</h2>"]
    for en in entries:
        right = _e(en["dates"])
        head = f"<b>{_e(en['title'])}</b>"
        if en.get("org"):
            head += f" — {_e(en['org'])}"
        if en.get("link"):
            head += f" · <a href='{_e(en['link'])}'>{_e(en['link'])}</a>"
        out.append(f"<p class='row'>{head}{'  <span class=d>' + right + '</span>' if right else ''}</p>")
        if en["bullets"]:
            out.append("<ul>" + "".join(f"<li>{_e(b)}</li>" for b in en["bullets"]) + "</ul>")
    return "".join(out)


def _list(title, items):
    return f"<h2>{title}</h2><ul>" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>" if items else ""


def render(cv: dict) -> str:
    """One-column, ATS-friendly HTML (every field escaped). Google Docs converts it faithfully."""
    contact = " · ".join(_e(x) for x in (cv["email"], cv["phone"], cv["city"]) if x)
    links = " · ".join(f"<a href='{_e(l['url'])}'>{_e(l['label'] or l['url'])}</a>" for l in cv["links"] if l.get("url"))
    edu = "".join(
        f"<p class='row'><b>{_e(e['institution'])}</b> — {_e(e['degree'])}"
        f"{'  <span class=d>' + _e(e['dates']) + '</span>' if e['dates'] else ''}</p>"
        + (f"<p>{_e(e['details'])}</p>" if e["details"] else "") for e in cv["education"])
    skills = "".join(f"<p><b>{_e(s['label'])}:</b> {_e(', '.join(s['items']))}</p>" for s in cv["skills"] if s["items"])
    return (
        "<html><head><meta charset='utf-8'><style>"
        "body{font-family:Arial;font-size:10.5pt;line-height:1.3;color:#111}"
        "h1{font-size:20pt;margin:0;text-align:center} .c{text-align:center;color:#333;margin:2px 0}"
        "h2{font-size:11.5pt;color:#1e3a8a;text-transform:uppercase;border-bottom:1px solid #1e3a8a;"
        "margin:12px 0 4px} p{margin:2px 0} ul{margin:2px 0 6px 18px;padding:0} li{margin:1px 0}"
        ".d{color:#555;float:right} a{color:#1d4ed8}"
        f"</style></head><body><h1>{_e(cv['name'])}</h1>"
        + (f"<p class='c'>{_e(cv['headline'])}</p>" if cv["headline"] else "")
        + (f"<p class='c'>{contact}</p>" if contact else "")
        + (f"<p class='c'>{links}</p>" if links else "")
        + (f"<h2>Summary</h2><p>{_e(cv['summary'])}</p>" if cv["summary"] else "")
        + (f"<h2>Education</h2>{edu}" if edu else "")
        + (f"<h2>Skills</h2>{skills}" if skills else "")
        + _entries("Projects", cv["projects"])
        + _entries("Experience", cv["experience"])
        + _list("Achievements", cv["achievements"])
        + _list("Certifications", cv["certifications"])
        + _list("Activities", cv["activities"])
        + "</body></html>")


# ---------------------------------------------------------------- Drive + PDF
def build(cv: dict) -> dict:
    """Write/refresh the Google Doc, export the PDF, and make it the CV used for applications."""
    from tools import notes_tools as nt
    old = db.kv_get("cv_draft") or {}
    page = render(cv)
    svc = g.drive()
    folder = nt._folder("Internships", nt._folder("StudyPilot"))
    title = f"{cv['name'] or 'My'} — CV"
    doc = None
    if old.get("doc_id"):
        try:
            media = MediaIoBaseUpload(io.BytesIO(page.encode("utf-8")), mimetype="text/html")
            doc = g.with_retry(lambda: svc.files().update(fileId=old["doc_id"], body={"name": title},
                                                         media_body=media, fields="id,webViewLink").execute())
        except Exception:
            doc = None
    if not doc:
        media = MediaIoBaseUpload(io.BytesIO(page.encode("utf-8")), mimetype="text/html")
        doc = g.with_retry(lambda: svc.files().create(body={"name": title, "mimeType": DOC, "parents": [folder]},
                                                     media_body=media, fields="id,webViewLink").execute())
    pdf = g.with_retry(lambda: svc.files().export(fileId=doc["id"], mimeType="application/pdf").execute())
    draft = {"cv": cv, "doc_id": doc["id"], "doc_link": doc["webViewLink"],
             "version": (old.get("version") or 0) + 1, "updated": time.time()}
    db.kv_set("cv_draft", draft)
    log(AGENT, f"📄 Drafted your CV (version {draft['version']}): saved to Drive as a Google Doc and PDF.", "success")
    career.save_cv(pdf)    # the internship agent now uses this CV + profile
    refresh()
    return draft


def get_draft():
    return db.kv_get("cv_draft")


def pdf_bytes():
    d = get_draft()
    if not d:
        return None
    return g.with_retry(lambda: g.drive().files().export(fileId=d["doc_id"], mimeType="application/pdf").execute())


def _doc_text(d):
    try:
        raw = g.with_retry(lambda: g.drive().files().export(fileId=d["doc_id"], mimeType="text/plain").execute())
        return raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else str(raw)
    except Exception:
        return ""


def ai_edit(instruction: str) -> dict:
    """'Make it one page', 'add my new project…', 'more backend-focused'. Reads the Google Doc first,
    so the student's own edits there are kept."""
    d = get_draft()
    if not d:
        raise ValueError("No CV yet. Build one first.")
    text = _doc_text(d)
    cv = gemini.generate_json(
        "Here is the student's current CV (the Google Doc text is the latest — it may include their "
        "own edits) and their instruction. Return the full updated CV. Keep everything true; only add "
        "facts the instruction itself gives.\n\nINSTRUCTION: " + instruction
        + "\n\nCURRENT CV (Google Doc text, includes the student's own edits):\n" + (text or "")[:6000]
        + "\n\nLAST STRUCTURED VERSION (keep its links/contact details unless the Doc changed them):\n"
        + json.dumps(d["cv"], ensure_ascii=False)[:5000],
        CV, system=SYSTEM)
    log(AGENT, f"✏️ Updating your CV: “{instruction[:80]}”")
    return build(cv)


def sync_from_doc() -> dict:
    """The student edited the Google Doc by hand: re-export it and use it for applications."""
    d = get_draft()
    if not d:
        raise ValueError("No CV yet.")
    pdf = pdf_bytes()
    career.save_cv(pdf)
    d["updated"] = time.time()
    db.kv_set("cv_draft", d)
    log(AGENT, "🔄 Picked up your edits from the Google Doc — applications will use the new CV.", "success")
    refresh()
    return d
