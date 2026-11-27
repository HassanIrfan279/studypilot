"""Career agent: finds internships that fit the student, decides which to apply to, writes each
application, and tracks replies in Gmail by itself.

The loop:  profile (from CV) -> discover -> evaluate & decide -> write -> student approves ->
           (student sends) -> watch Gmail -> update status -> act (prep sessions, follow-ups, alerts)

Boundaries (on purpose):
- It never sends or submits anything in the student's name. Applications become Gmail DRAFTS
  (email postings) or copy-ready answers (portal postings); the student presses Send/Submit.
- It never invents experience. Anything it doesn't know becomes a question for the student.
- Sources are the student's own job-alert emails, Gemini Google Search (when the API key allows
  it), public remote-job APIs, and postings the student pastes in. No scraping of LinkedIn.
"""
import base64
import hashlib
import json
import re
import threading
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import requests
from pydantic import BaseModel

import db
import gemini
import runs
import google_clients as g
from activity_log import announce, log, refresh
from config import DATA_DIR, MODEL_CHAIN, TIMEZONE
from tools import notify

AGENT = "Career"
TZ = ZoneInfo(TIMEZONE)
CV_PATH = DATA_DIR / "cv.pdf"
COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
MAX_NEW_APPS_PER_RUN = 3        # be selective: a few strong applications beat many weak ones
FOLLOW_UP_AFTER_DAYS = 10
STATUSES = ["found", "shortlisted", "needs_info", "ready", "applied", "interview", "offer",
            "rejected", "skipped"]

db.execute("""CREATE TABLE IF NOT EXISTS internships (
    id TEXT PRIMARY KEY, title TEXT, company TEXT, location TEXT, url TEXT, source TEXT,
    deadline TEXT, description TEXT, apply_method TEXT, apply_email TEXT,
    score INTEGER, decision TEXT, reasoning TEXT, red_flags TEXT, timing_note TEXT,
    status TEXT, app TEXT, questions TEXT, doc_link TEXT, draft_id TEXT,
    created REAL, updated REAL, applied_at REAL, followup_at REAL, timeline TEXT)""")

_lock = threading.Lock()   # one pipeline run at a time
_run_id = None             # current "Decisions" panel run while a search is going


def _log(msg, level="info", kind=None):
    """Live log + a step in the Decisions panel (when a search run is open)."""
    log(AGENT, msg, level)
    if _run_id:
        try:
            runs.step(_run_id, kind or {"success": "ok", "warn": "warn", "error": "warn"}.get(level, "act"), msg)
        except Exception:
            pass


# ---------------------------------------------------------------- schemas
class Project(BaseModel):
    name: str
    summary: str
    tech: list[str]
    link: str


class CareerProfile(BaseModel):
    name: str
    email: str
    phone: str
    city: str
    university: str
    degree: str
    semester: str
    cgpa: str
    skills: list[str]
    projects: list[Project]
    experience: list[str]
    links: list[str]
    preferred_roles: list[str]
    preferred_locations: list[str]
    open_to_remote: bool
    gaps: list[str]            # important things missing from the CV, phrased as questions


class Posting(BaseModel):
    title: str
    company: str
    location: str
    link_index: int            # index into the numbered link list, -1 if none
    deadline: str              # YYYY-MM-DD or ""
    apply_email: str
    description: str
    is_internship: bool        # internship / trainee / fresh-graduate role


class Postings(BaseModel):
    postings: list[Posting]


class Verdict(BaseModel):
    id: str
    score: int                 # 0-100 fit
    decision: str              # apply | maybe | skip
    reasoning: str
    red_flags: list[str]
    timing_note: str


class Verdicts(BaseModel):
    verdicts: list[Verdict]


class QA(BaseModel):
    question: str
    answer: str


class Application(BaseModel):
    subject: str
    cover_letter: str
    cv_highlights: list[str]
    answers: list[QA]
    questions_for_student: list[str]


class Reply(BaseModel):
    message_index: int
    internship_id: str         # "" if it isn't about any tracked application
    kind: str                  # interview | assessment | offer | rejection | acknowledgement | other
    summary: str
    event_date: str            # YYYY-MM-DD or ""
    event_time: str            # HH:MM or ""


class Replies(BaseModel):
    replies: list[Reply]


class FollowUp(BaseModel):
    subject: str
    body: str


SYSTEM = ("You are StudyPilot's career agent for a university student in Pakistan. You are "
          "honest and selective. NEVER invent skills, projects, grades or experience: use only "
          "facts from the student's profile. If something needed is unknown, ask instead. "
          "Write in clear, confident, plain English — no clichés like 'I am writing to express'. "
          "When talking ABOUT the student (reasons, notes), address them as 'you' — never he/she.")


# ---------------------------------------------------------------- helpers
def _now():
    return time.time()


def _row(r):
    if not r:
        return None
    d = dict(r)
    for k in ("red_flags", "app", "questions", "timeline"):
        try:
            d[k] = json.loads(d[k]) if d.get(k) else ([] if k != "app" else None)
        except ValueError:
            d[k] = [] if k != "app" else None
    return d


def get(iid):
    return _row(db.one("SELECT * FROM internships WHERE id=?", (iid,)))


def all_items():
    return [_row(r) for r in db.query("SELECT * FROM internships ORDER BY score DESC, created DESC")]


def _set(iid, **fields):
    for k in ("red_flags", "app", "questions", "timeline"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k])
    fields["updated"] = _now()
    cols = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE internships SET {cols} WHERE id=?", (*fields.values(), iid))


def _event(iid, text):
    it = get(iid)
    tl = (it and it["timeline"]) or []
    tl.append({"ts": _now(), "text": text})
    _set(iid, timeline=tl[-30:])


def _id_for(company, title, url):
    base = (url or f"{company}|{title}").lower().strip()
    return "in-" + hashlib.sha1(base.encode()).hexdigest()[:12]


def _clean_url(u):
    u = u.strip().rstrip(").,>\"'")
    m = re.search(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", u)
    if m:
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}"
    return u


def _gmail():
    return g._service("gmail", "v1")


def has_compose():
    granted = set((db.kv_get("token") or {}).get("scopes") or [])
    return COMPOSE in granted


def _upcoming_exams():
    rows = db.query("SELECT title, due FROM items WHERE active=1 AND due > ? ORDER BY due LIMIT 8",
                    (datetime.now(TZ).isoformat(),))
    return "; ".join(f"{r['title']} ({r['due'][:10]})" for r in rows) or "none"


# ---------------------------------------------------------------- profile
def profile():
    return db.kv_get("career_profile")


def save_cv(pdf_bytes: bytes):
    """Read the CV with Gemini and build the career profile. Returns the profile."""
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Please upload your CV as a PDF.")
    CV_PATH.write_bytes(pdf_bytes)
    _log("📄 Reading your CV…")
    about = db.kv_get("profile") or {}
    prof = gemini.generate_json(
        "Extract this student's career profile from the CV. Use ONLY what the CV says; leave a "
        "field empty if it isn't there. preferred_roles: 3-5 internship roles that fit their skills. "
        "preferred_locations: their city plus 'Remote' if sensible. gaps: up to 4 short questions "
        "about IMPORTANT missing things an internship application needs (e.g. no GitHub/portfolio "
        "link, no CGPA, no graduation year). Extra context from their StudyPilot interview: "
        + json.dumps(about)[:1500],
        CareerProfile, parts=[gemini.file_part(pdf_bytes, "application/pdf")], system=SYSTEM)
    db.kv_set("career_profile", prof)
    db.kv_set("career_answers", db.kv_get("career_answers") or {})
    _log(f"Profile ready: {len(prof['skills'])} skills, {len(prof['projects'])} projects. "
               f"Looking for: {', '.join(prof['preferred_roles'][:3])}.", "success")
    refresh()
    return prof


def update_profile(patch: dict):
    prof = profile() or {}
    allowed = {"preferred_roles", "preferred_locations", "open_to_remote", "links", "cgpa",
               "semester", "skills"}
    prof.update({k: v for k, v in patch.items() if k in allowed})
    db.kv_set("career_profile", prof)
    return prof


def answer_gap(question: str, answer: str):
    """The student answered one of the agent's questions; remember it for every application."""
    answers = db.kv_get("career_answers") or {}
    answers[question] = answer
    db.kv_set("career_answers", answers)
    prof = profile()
    if prof and question in prof.get("gaps", []):
        prof["gaps"] = [q for q in prof["gaps"] if q != question]
        db.kv_set("career_profile", prof)
    # Applications that were waiting on this answer can be finished now
    waiting = [it for it in all_items() if it["status"] == "needs_info" and question in (it["questions"] or [])]
    for it in waiting:
        rest = [q for q in it["questions"] if q not in answers]
        _set(it["id"], questions=rest)
        if not rest:
            threading.Thread(target=_safe_write, args=(it["id"],), daemon=True).start()
    return {"ok": True, "unblocked": len(waiting)}


def _facts():
    prof = profile() or {}
    answers = db.kv_get("career_answers") or {}
    return json.dumps({"profile": {k: v for k, v in prof.items() if k != "gaps"},
                       "extra_facts_from_student": answers}, ensure_ascii=False)[:6000]


# ---------------------------------------------------------------- discovery
def _from_gmail():
    """Job-alert emails (LinkedIn, Rozee, Indeed, career office) -> postings with real links."""
    svc = _gmail()
    q = ('newer_than:21d (internship OR intern OR trainee OR "graduate program" OR "job alert" '
         'OR "jobs for you") -category:promotions')
    ids = g.with_retry(lambda: svc.users().messages().list(userId="me", q=q, maxResults=12)
                       .execute()).get("messages", [])
    seen = set(db.kv_get("career_seen_mail") or [])
    from tools.gmail_tools import _text
    out = []
    fresh = [m for m in ids if m["id"] not in seen]
    for m in fresh[:8]:
        full = g.with_retry(lambda: svc.users().messages().get(userId="me", id=m["id"], format="full").execute())
        hdr = {h["name"].lower(): h["value"] for h in full["payload"].get("headers", [])}
        text = re.sub(r"\s+", " ", _text(full["payload"]))
        links = []
        for u in re.findall(r"https?://[^\s<>\"']+", text):
            cu = _clean_url(u)
            if any(s in cu for s in ("unsubscribe", "/help/", "settings", "privacy", "/feed", "googleusercontent",
                                     ".png", ".jpg", "/psettings", "/mypreferences")):
                continue
            if cu not in links:
                links.append(cu)
        links = links[:40]
        numbered = "\n".join(f"[{i}] {u}" for i, u in enumerate(links))
        try:
            res = gemini.generate_json(
                "List every job/internship posting in this email. For each give the link_index of "
                "its own link from the numbered list (or -1). is_internship = true only for "
                "internships, trainee or fresh-graduate roles a university student could apply to.\n\n"
                f"From: {hdr.get('from', '')}\nSubject: {hdr.get('subject', '')}\n\n{text[:6000]}\n\n"
                f"LINKS:\n{numbered}", Postings, system=SYSTEM)
        except Exception as e:
            _log(f"Couldn't read one job email ({type(e).__name__}).", "warn")
            continue
        for p in res["postings"]:
            if not p["is_internship"]:
                continue
            url = links[p["link_index"]] if 0 <= p["link_index"] < len(links) else ""
            out.append({**p, "url": url, "source": "Gmail · " + (hdr.get("from", "").split("<")[0].strip()[:40] or "email")})
        seen.add(m["id"])
    db.kv_set("career_seen_mail", list(seen)[-300:])
    return out


def _from_web(prof):
    """Gemini + Google Search grounding: live postings from the open web (Pakistan + remote)."""
    off_until = db.kv_get("career_web_off_until") or 0
    if _now() < off_until:
        return []
    from google.genai import types
    roles = ", ".join(prof.get("preferred_roles", [])[:4]) or "software engineering"
    places = ", ".join(prof.get("preferred_locations", [])[:3]) or "Pakistan, Remote"
    try:
        r = gemini.client.models.generate_content(
            model=MODEL_CHAIN[0],
            contents=(f"Find up to 8 internship openings that are open right now for a university "
                      f"student. Roles: {roles}. Locations: {places}. Prefer postings from the last "
                      "30 days on company career pages, Rozee.pk, LinkedIn or university notices. "
                      "For each: company, role, city, deadline if shown, how to apply."),
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                http_options=types.HttpOptions(timeout=60_000)))
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            db.kv_set("career_web_off_until", _now() + 6 * 3600)
            _log("Web search isn't enabled on this Gemini API key yet (quota 0) — using job "
                       "emails and job boards instead.", "warn")
        else:
            _log(f"Web search failed ({type(e).__name__}); using other sources.", "warn")
        return []
    gm = r.candidates[0].grounding_metadata if r.candidates else None
    chunks = [c.web for c in (gm.grounding_chunks or [])] if gm else []
    links = [c.uri for c in chunks if c and c.uri]
    numbered = "\n".join(f"[{i}] {c.title}" for i, c in enumerate(chunks) if c)
    res = gemini.generate_json(
        "Turn these search findings into postings. link_index must point at the source the "
        f"posting came from.\n\n{r.text or ''}\n\nSOURCES:\n{numbered}", Postings, system=SYSTEM)
    out = []
    for p in res["postings"]:
        if not p["is_internship"]:
            continue
        url = links[p["link_index"]] if 0 <= p["link_index"] < len(links) else ""
        if url:
            try:  # grounding links are redirects -> resolve to the real page, drop dead ones
                h = requests.get(url, allow_redirects=True, timeout=10, stream=True,
                                 headers={"User-Agent": "Mozilla/5.0 StudyPilot"})
                h.close()
                if h.status_code == 404 or h.status_code == 410:
                    continue
                url = h.url
            except requests.RequestException:
                continue
        out.append({**p, "url": url, "source": "Web search"})
    return out


def _from_bayt(prof):
    """Bayt.com Pakistan search pages (robots.txt allows them): a few searches from the target roles."""
    import html as _h
    import urllib.robotparser as rp
    UA = "Mozilla/5.0 (compatible; StudyPilot/1.0; student internship helper)"
    robots = rp.RobotFileParser()
    try:
        robots.parse(requests.get("https://www.bayt.com/robots.txt", headers={"User-Agent": UA}, timeout=10).text.splitlines())
    except requests.RequestException:
        return []
    slugs = []
    for r in (prof.get("preferred_roles") or [])[:3] + ["internship", "trainee"]:
        slug = re.sub(r"[^a-z0-9]+", "-", r.lower()).strip("-")
        if slug and slug not in slugs:
            slugs.append(slug)
    cards, links = [], []
    for slug in slugs[:5]:
        url = f"https://www.bayt.com/en/pakistan/jobs/{slug}-jobs/"
        if not robots.can_fetch(UA, url):
            continue
        try:
            page = requests.get(url, headers={"User-Agent": UA}, timeout=15).text
        except requests.RequestException:
            continue
        for card in re.findall(r"<li[^>]*data-js-job[^>]*>(.*?)</li>", page, flags=re.S):
            m = re.search(r'href="(/en/pakistan/jobs/[^"]+-\d+/)"', card)
            if not m or ("https://www.bayt.com" + m.group(1)) in links:
                continue
            links.append("https://www.bayt.com" + m.group(1))
            text = re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", card))).strip()
            cards.append(f"[{len(links) - 1}] {text[:450]}")
        time.sleep(1)  # be gentle
    if not cards:
        return []
    res = gemini.generate_json(
        "These are job cards from Bayt.com Pakistan. Return each one as a posting; link_index is the "
        "number in brackets. is_internship = true ONLY if the card itself says intern/internship, "
        "trainee, graduate/fresh graduate, entry level or junior, or asks for 0-1 years; otherwise false.\n\n"
        + "\n".join(cards[:45]), Postings, system=SYSTEM)
    return [{**p, "url": links[p["link_index"]] if 0 <= p["link_index"] < len(links) else "", "source": "Bayt.com"}
            for p in res["postings"] if p["is_internship"]]


def _from_boards():
    """Public remote-job APIs, internships only, open to candidates worldwide/Asia."""
    H = {"User-Agent": "StudyPilot/1.0 (student internship helper)"}
    out = []
    intern = re.compile(r"\b(intern|internship|trainee|graduate program)\b", re.I)
    ok_geo = re.compile(r"(worldwide|anywhere|global|asia|apac|pakistan|emea)", re.I)
    try:
        for j in requests.get("https://remotive.com/api/remote-jobs?search=intern&limit=50",
                              headers=H, timeout=15).json().get("jobs", []):
            if intern.search(j["title"]) and ok_geo.search(j.get("candidate_required_location") or ""):
                out.append({"title": j["title"], "company": j["company_name"],
                            "location": "Remote · " + j.get("candidate_required_location", ""),
                            "url": j["url"], "deadline": "", "apply_email": "",
                            "description": re.sub(r"<[^>]+>", " ", j.get("description", ""))[:1500],
                            "source": "Remotive"})
    except Exception:
        pass
    try:
        for j in requests.get("https://jobicy.com/api/v2/remote-jobs?count=50", headers=H,
                              timeout=15).json().get("jobs", []):
            if intern.search(j["jobTitle"]) and ok_geo.search(str(j.get("jobGeo", ""))):
                out.append({"title": j["jobTitle"], "company": j["companyName"],
                            "location": "Remote · " + str(j.get("jobGeo", "")), "url": j["url"],
                            "deadline": "", "apply_email": "",
                            "description": re.sub(r"<[^>]+>", " ", j.get("jobExcerpt", ""))[:1500],
                            "source": "Jobicy"})
    except Exception:
        pass
    return out


def _store(postings):
    """Insert new postings; returns the ids that are new."""
    new = []
    for p in postings:
        title, company = (p.get("title") or "").strip(), (p.get("company") or "").strip()
        if not title or not company:
            continue
        url = _clean_url(p.get("url") or "")
        iid = _id_for(company, title, url)
        dup = db.one("SELECT id FROM internships WHERE id=? OR (lower(company)=lower(?) AND lower(title)=lower(?))",
                     (iid, company, title))
        if dup:
            continue
        db.execute("INSERT INTO internships(id, title, company, location, url, source, deadline, "
                   "description, apply_email, status, created, updated, timeline) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (iid, title, company, p.get("location", ""), url, p.get("source", ""),
                    p.get("deadline", ""), p.get("description", "")[:3000],
                    (p.get("apply_email") or "").strip(), "found", _now(), _now(),
                    json.dumps([{"ts": _now(), "text": f"Found via {p.get('source', 'search')}"}])))
        new.append(iid)
    return new


def add_manual(text: str = "", url: str = ""):
    """The student pasted a posting (text and/or link). Fetch the page if allowed, then evaluate."""
    body = text.strip()
    if url and not body and "linkedin.com" not in url:
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 StudyPilot"})
            r.raise_for_status()
            body = re.sub(r"\s+", " ", re.sub(r"<(script|style).*?</\1>|<[^>]+>", " ", r.text, flags=re.S))[:8000]
        except Exception:
            body = ""
    if not body:
        raise ValueError("Couldn't read that page. Paste the posting's text instead.")
    res = gemini.generate_json(
        "Extract the job/internship posting from this text. link_index = 0 if a link is given, else -1. "
        "is_internship = true for internships, trainee or fresh-graduate roles.\n\n" + body
        + (f"\n\nLINKS:\n[0] {url}" if url else ""), Postings, system=SYSTEM)
    posts = [{**p, "url": url if p["link_index"] == 0 else "", "source": "Added by you"}
             for p in res["postings"][:1]]
    if not posts:
        raise ValueError("I couldn't find a job posting in that text.")
    new = _store(posts)
    if not new:
        return {"ok": True, "duplicate": True}
    _log(f"➕ Added {posts[0]['title']} at {posts[0]['company']}. Judging the fit…")
    _evaluate(new)
    it = get(new[0])
    if it["status"] == "shortlisted":
        _safe_write(new[0])
    refresh()
    return {"ok": True, "id": new[0]}


# ---------------------------------------------------------------- decide
def _evaluate(ids):
    items = [get(i) for i in ids]
    items = [i for i in items if i]
    if not items:
        return
    listing = "\n\n".join(
        f"id={i['id']}\n{i['title']} — {i['company']} ({i['location']})\nSource: {i['source']}\n"
        f"Deadline: {i['deadline'] or 'not stated'}\n{(i['description'] or '')[:900]}" for i in items)
    res = gemini.generate_json(
        "Decide which of these postings this student should apply to. Score 0-100 for real fit "
        "(skills/projects match, level suitable for their semester, location or remote, field). "
        "decision: 'apply' (score >= 65 and a real fit), 'maybe' (partly fits, e.g. on-site in another "
        "city, slightly senior, or a stretch skill), or 'skip' ONLY for a different field, a clearly "
        "wrong level (e.g. senior/lead, 3+ years required) or a scam. A different city, commuting or "
        "upcoming exams are NEVER a reason to skip: mention them in timing_note instead. Treat on-site "
        "roles in big cities near the student as fine unless they said otherwise. reasoning: "
        "2 short sentences naming the concrete match or mismatch, addressed to the student as 'you'. red_flags: scam signs (asks for "
        "a fee/deposit, vague company, personal Gmail recruiter + too-good pay), or level mismatch. "
        "A posting that is not clearly an internship, trainee or entry-level role can be at most "
        "'maybe'. Any posting asking the student to pay must be 'skip'. timing_note: one line about the "
        f"deadline vs their upcoming exams ({_upcoming_exams()}), or \"\".\n\n"
        f"STUDENT:\n{_facts()}\n\nPOSTINGS:\n{listing}", Verdicts, system=SYSTEM)
    by_id = {i["id"]: i for i in items}
    for v in res["verdicts"]:
        if v["id"] not in by_id:
            continue
        decision = v["decision"] if v["decision"] in ("apply", "maybe", "skip") else "maybe"
        if v["red_flags"] and any(w in " ".join(v["red_flags"]).lower() for w in ("fee", "deposit", "scam", "pay to")):
            decision = "skip"
        entry_level = re.search(r"(?i)\b(intern|internship|trainee|graduate|fresh|entry|junior|apprentice)",
                                by_id[v["id"]]["title"] + " " + (by_id[v["id"]]["description"] or "")[:400])
        if decision == "apply" and not entry_level:
            decision = "maybe"   # never auto-apply to a regular job
        status = {"apply": "shortlisted", "skip": "skipped"}.get(decision, "found")
        _set(v["id"], score=max(0, min(100, int(v["score"]))), decision=decision,
             reasoning=v["reasoning"], red_flags=v["red_flags"], timing_note=v["timing_note"], status=status)
        verb = {"apply": "✅ Will apply", "skip": "⏭ Skipping", "maybe": "🤔 Maybe"}[decision]
        _event(v["id"], f"{verb} ({v['score']}/100): {v['reasoning']}")
        it = by_id[v["id"]]
        _log(f"{verb}: {it['title']} at {it['company']} — {v['score']}/100. {v['reasoning']}",
            "success" if decision == "apply" else "info")


# ---------------------------------------------------------------- write
def _safe_write(iid):
    try:
        write_application(iid)
    except Exception as e:
        _log(f"Couldn't write the application ({type(e).__name__}: {str(e)[:120]}).", "error")


def write_application(iid, instruction=""):
    it = get(iid)
    if not it:
        return None
    _log(f"✍️ Writing the application for {it['title']} at {it['company']}…")
    method = "email" if it.get("apply_email") else "portal"
    res = gemini.generate_json(
        f"Write this student's application for the posting below. Apply method: {method}. "
        "cover_letter: 150-220 words in 3-4 short paragraphs separated by blank lines, specific to "
        "THIS company and role, built on 1-2 of the student's most relevant real projects/skills, "
        "ending with a polite ask; sign with the student's name. Availability, start dates, stipend "
        "expectations, CGPA and contact details: state them ONLY if they are in the facts; otherwise "
        "leave them out of the letter and, in form answers, write a neutral line (e.g. 'Happy to "
        "discuss') — never invent a date, amount or number. subject: an email subject line. cv_highlights: 3-5 CV "
        "bullets reordered/reworded (truthfully) for this role. answers: likely application-form "
        "questions for this posting (why this company, relevant project, availability, expected "
        "stipend if asked, etc.) with ready answers. questions_for_student: ONLY facts you truly "
        "need and don't have (max 3); if you can write a strong application without them, return "
        "an empty list. Never make up facts."
        + (f"\nStudent's instruction for this rewrite: {instruction}" if instruction else "")
        + f"\n\nSTUDENT:\n{_facts()}\n\nPOSTING:\n{it['title']} — {it['company']} ({it['location']})\n"
          f"{(it['description'] or '')[:3000]}", Application, system=SYSTEM)
    answers = db.kv_get("career_answers") or {}
    open_q = [q for q in res["questions_for_student"] if q not in answers][:3]
    _set(iid, app=res, apply_method=method, questions=open_q,
         status="needs_info" if open_q else "ready")
    if open_q:
        _event(iid, "Needs your input: " + " / ".join(open_q))
        _log(f"❓ To finish {it['company']} I need: {' / '.join(open_q)}", "warn")
    else:
        _event(iid, "Application written — waiting for your approval")
        _log(f"📝 Application for {it['title']} at {it['company']} is ready for your approval.", "success")
    threading.Thread(target=_save_doc, args=(iid,), daemon=True).start()
    refresh()
    return get(iid)


def edit_application(iid, cover_letter=None, subject=None):
    it = get(iid)
    app = it["app"] or {}
    if cover_letter is not None:
        app["cover_letter"] = cover_letter
    if subject is not None:
        app["subject"] = subject
    _set(iid, app=app)
    return get(iid)


def _save_doc(iid):
    """Keep a copy of every application in Drive: StudyPilot/Internships/<Company — Role>."""
    try:
        from googleapiclient.http import MediaIoBaseUpload
        import io
        from tools import notes_tools as nt
        it = get(iid)
        app = it["app"]
        md = (f"# {it['title']} — {it['company']}\n\n**Location:** {it['location']}  \n"
              f"**Link:** {it['url'] or '—'}  \n**Fit:** {it['score']}/100 — {it['reasoning']}\n\n"
              f"## Cover letter\n\n**Subject:** {app['subject']}\n\n{app['cover_letter']}\n\n"
              "## CV highlights for this role\n\n" + "\n".join(f"- {b}" for b in app["cv_highlights"])
              + "\n\n## Ready answers\n\n" + "\n\n".join(f"**{qa['question']}**\n\n{qa['answer']}" for qa in app["answers"]))
        folder = nt._folder("Internships", nt._folder("StudyPilot"))
        svc = g.drive()
        name = f"{it['company']} — {it['title']}"[:100]
        media = MediaIoBaseUpload(io.BytesIO(nt._html(md, name).encode("utf-8")), mimetype="text/html")
        doc = g.with_retry(lambda: svc.files().create(
            body={"name": name, "mimeType": "application/vnd.google-apps.document", "parents": [folder]},
            media_body=media, fields="id,webViewLink").execute())
        _set(iid, doc_link=doc["webViewLink"])
    except Exception as e:
        _log(f"Couldn't save the application to Drive ({type(e).__name__}).", "warn")


# ---------------------------------------------------------------- approve (student-in-the-loop)
def _draft(to, subject, body, attach_cv=True, thread_id=None):
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if attach_cv and CV_PATH.exists():
        prof = profile() or {}
        fname = (re.sub(r"[^A-Za-z0-9]+", "_", prof.get("name") or "Student").strip("_") + "_CV.pdf")
        msg.add_attachment(CV_PATH.read_bytes(), maintype="application", subtype="pdf", filename=fname)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body = {"message": {"raw": raw, **({"threadId": thread_id} if thread_id else {})}}
    d = g.with_retry(lambda: _gmail().users().drafts().create(userId="me", body=body).execute())
    return d["id"], f"https://mail.google.com/mail/u/0/#drafts?compose={d['message']['id']}"


def approve(iid):
    """Student approved. Email postings -> a Gmail DRAFT with the CV attached (the student sends
    it). Portal postings -> the student opens the link with the ready answers."""
    it = get(iid)
    if not it or not it["app"]:
        raise ValueError("No application written yet.")
    app = it["app"]
    if it["apply_method"] == "email" and it["apply_email"]:
        if has_compose():
            draft_id, link = _draft(it["apply_email"], app["subject"], app["cover_letter"])
            _set(iid, draft_id=draft_id)
            _event(iid, "Approved — Gmail draft created with your CV attached. Press Send in Gmail.")
            _log(f"📨 Draft ready in Gmail for {it['company']} (CV attached). Review and press Send — "
                       "I'll notice when it's sent.", "success")
            refresh()
            return {"method": "email", "open": link, "draft": True}
        from urllib.parse import quote
        link = (f"https://mail.google.com/mail/?view=cm&fs=1&to={quote(it['apply_email'])}"
                f"&su={quote(app['subject'])}&body={quote(app['cover_letter'])}")
        _event(iid, "Approved — opened Gmail compose (attach your CV, then Send).")
        return {"method": "email", "open": link, "draft": False,
                "note": "Sign in again to let StudyPilot attach your CV automatically. For now, attach it yourself."}
    _event(iid, "Approved — opened the application page. Paste the ready answers, then mark it submitted.")
    return {"method": "portal", "open": it["url"]}


def mark_applied(iid):
    _set(iid, status="applied", applied_at=_now())
    it = get(iid)
    _event(iid, "Application sent ✅ — tracking replies in Gmail")
    _log(f"✅ Applied: {it['title']} at {it['company']}. I'll watch Gmail for their reply.", "success")
    refresh()
    return it


def set_status(iid, status):
    if status not in STATUSES:
        raise ValueError("bad status")
    if status == "applied":
        return mark_applied(iid)
    _set(iid, status=status)
    _event(iid, f"Moved to {status} by you")
    refresh()
    return get(iid)


# ---------------------------------------------------------------- track (runs by itself)
def _sent_check():
    """Email applications: notice when the student actually sent the draft."""
    for it in all_items():
        if it["status"] != "ready" or not it["apply_email"] or not it["draft_id"]:
            continue
        q = f'in:sent to:{it["apply_email"]} after:{int(it["updated"] or it["created"]) - 60}'
        sent = g.with_retry(lambda: _gmail().users().messages().list(userId="me", q=q, maxResults=1)
                            .execute()).get("messages")
        if sent:
            mark_applied(it["id"])


def _book_prep(it, when_date, kind):
    """Interview/assessment invite -> book a prep session before it, tagged as StudyPilot's."""
    from tools import calendar_tools as cal
    try:
        day = datetime.fromisoformat(when_date).replace(tzinfo=TZ) if when_date else datetime.now(TZ) + timedelta(days=3)
    except ValueError:
        day = datetime.now(TZ) + timedelta(days=3)
    slot = cal.find_free_slot(60, datetime.now(TZ) + timedelta(hours=2), day)
    if not slot:
        return None
    start, end = slot
    body = {"summary": f"💼 {kind.title()} prep: {it['company']} ({it['title']})",
            "description": f"StudyPilot career agent.\nReview your application and practise answers.\n{it['doc_link'] or ''}",
            "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
            "colorId": "3",
            "extendedProperties": {"private": {"studypilot": "true", "kind": "career", "internship_id": it["id"]}}}
    cal._insert_once(g.calendar(), body)
    return start


def _interview_pack(iid):
    it = get(iid)
    try:
        qs = gemini.generate_text(
            "Write a short interview-prep sheet in markdown for this internship: 8 likely questions "
            "(technical for this role + behavioural) each with a strong answer outline built ONLY on "
            f"the student's real profile, plus 3 smart questions to ask them.\n\nSTUDENT:\n{_facts()}\n\n"
            f"ROLE: {it['title']} at {it['company']}\n{(it['description'] or '')[:2000]}", system=SYSTEM)
        app = it["app"] or {}
        app["interview_prep"] = qs
        _set(iid, app=app)
    except Exception:
        pass


def _replies():
    """Read new emails about tracked applications and move each application along by itself."""
    tracked = [it for it in all_items() if it["status"] in ("ready", "applied", "interview")]
    if not tracked:
        return
    since = int(min((it["applied_at"] or it["updated"] or it["created"]) for it in tracked)) - 3600
    names = " OR ".join(f'"{it["company"]}"' for it in tracked[:15])
    q = f"after:{since} ({names}) -in:sent -in:drafts"
    ids = g.with_retry(lambda: _gmail().users().messages().list(userId="me", q=q, maxResults=15)
                       .execute()).get("messages", [])
    seen = set(db.kv_get("career_seen_replies") or [])
    fresh = [m for m in ids if m["id"] not in seen]
    if not fresh:
        return
    from tools.gmail_tools import _text
    msgs = []
    for m in fresh[:8]:
        full = g.with_retry(lambda: _gmail().users().messages().get(userId="me", id=m["id"], format="full").execute())
        hdr = {h["name"].lower(): h["value"] for h in full["payload"].get("headers", [])}
        msgs.append({"id": m["id"], "thread": full.get("threadId"), "from": hdr.get("from", ""),
                     "subject": hdr.get("subject", ""), "text": re.sub(r"\s+", " ", _text(full["payload"]))[:1500]})
    apps = "\n".join(f"id={it['id']}: {it['title']} at {it['company']} (status {it['status']})" for it in tracked)
    listing = "\n\n".join(f"[{i}] From: {m['from']}\nSubject: {m['subject']}\n{m['text']}" for i, m in enumerate(msgs))
    res = gemini.generate_json(
        "Match each email to the application it is about (internship_id, or \"\" if it is a job "
        "alert/newsletter or unrelated) and classify it: interview (invite or scheduling), "
        "assessment (test/task/coding challenge), offer, rejection, acknowledgement (we received "
        "your application), other. event_date/event_time: when the interview/assessment is, if "
        f"stated.\n\nAPPLICATIONS:\n{apps}\n\nEMAILS:\n{listing}", Replies, system=SYSTEM)
    by_id = {it["id"]: it for it in tracked}
    for r in res["replies"]:
        it = by_id.get(r["internship_id"])
        if not it or not (0 <= r["message_index"] < len(msgs)):
            continue
        kind = r["kind"]
        _event(it["id"], f"📩 {kind.title()}: {r['summary']}")
        if it["status"] == "ready" and kind != "other":
            _set(it["id"], status="applied", applied_at=_now())   # they replied, so it was sent
        if kind in ("interview", "assessment"):
            _set(it["id"], status="interview")
            start = _book_prep(it, r["event_date"], kind)
            threading.Thread(target=_interview_pack, args=(it["id"],), daemon=True).start()
            when = f" on {r['event_date']} {r['event_time']}".rstrip() if r["event_date"] else ""
            booked = f" I booked a prep session {start.strftime('%a %d %b, %I:%M %p')}." if start else ""
            what = "an interview" if kind == "interview" else "an assessment"
            msg = f"Good news! {it['company']} wants {what} for {it['title']}{when}.{booked} Your prep sheet is on the Internships page."
            announce(msg)
            notify.send("💼 StudyPilot: " + msg)
        elif kind == "offer":
            _set(it["id"], status="offer")
            msg = f"🎉 {it['company']} sent you an offer for {it['title']}! Check your email."
            announce(msg)
            notify.send("💼 StudyPilot: " + msg)
        elif kind == "rejection":
            _set(it["id"], status="rejected")
            _log(f"{it['company']} said no for {it['title']}. That's normal — I'll keep looking and "
                       "weight similar roles lower.", "warn")
        elif kind == "acknowledgement":
            _log(f"{it['company']} confirmed they received your application.", "info")
    db.kv_set("career_seen_replies", list(seen | {m["id"] for m in msgs})[-500:])
    refresh()


def _follow_ups():
    """No reply after 10 days -> write a polite follow-up as a draft for the student to approve."""
    for it in all_items():
        if it["status"] != "applied" or it["followup_at"] or not it["applied_at"]:
            continue
        if _now() - it["applied_at"] < FOLLOW_UP_AFTER_DAYS * 86400:
            continue
        try:
            fu = gemini.generate_json(
                f"Write a short, polite follow-up email (60-90 words) from the student about their "
                f"application for {it['title']} at {it['company']}, sent {FOLLOW_UP_AFTER_DAYS}+ days "
                f"ago. Restate one concrete strength.\n\nSTUDENT:\n{_facts()}", FollowUp, system=SYSTEM)
            app = it["app"] or {}
            app["follow_up"] = fu
            _set(it["id"], app=app, followup_at=_now())
            _event(it["id"], "No reply for 10 days — follow-up email written for your approval")
            _log(f"⏰ No reply from {it['company']} in {FOLLOW_UP_AFTER_DAYS} days. I wrote a "
                       "follow-up — approve it on the Internships page.", "warn")
        except Exception:
            pass


def approve_follow_up(iid):
    it = get(iid)
    fu = (it["app"] or {}).get("follow_up")
    if not fu:
        raise ValueError("No follow-up written.")
    if it["apply_email"] and has_compose():
        _, link = _draft(it["apply_email"], fu["subject"], fu["body"], attach_cv=False)
        _event(it["id"], "Follow-up draft created in Gmail")
        return {"open": link}
    from urllib.parse import quote
    return {"open": f"https://mail.google.com/mail/?view=cm&fs=1&to={quote(it['apply_email'] or '')}"
                    f"&su={quote(fu['subject'])}&body={quote(fu['body'])}"}


# ---------------------------------------------------------------- the loop
def run(force=False):
    """Full pipeline. Daily by itself, or when the student clicks 'Find internships now'."""
    global _run_id
    if not _lock.acquire(blocking=False):
        _log("Already searching — hang on.")
        return {"busy": True}
    try:
        prof = profile()
        if prof:
            _run_id = runs.start("career", "Internship search")
        if not prof:
            _log("Upload your CV on the Internships page so I know what to look for.", "warn")
            return {"needs_cv": True}
        _log("🔎 Looking for internships that fit you: job emails, web, Bayt.com, remote boards…")
        found = []
        for name, fn in (("job emails", _from_gmail), ("web search", lambda: _from_web(prof)),
                         ("Bayt.com Pakistan", lambda: _from_bayt(prof)), ("remote job boards", _from_boards)):
            try:
                got = fn()
                found += got
                if got:
                    _log(f"Found {len(got)} posting(s) in {name}.")
            except Exception as e:
                _log(f"Couldn't search {name} ({type(e).__name__}); continuing.", "warn")
        new = _store(found)
        _log(f"{len(new)} new posting(s) to judge." if new else "No new postings since last time.")
        for i in range(0, len(new), 12):
            try:
                _evaluate(new[i:i + 12])
            except Exception as e:
                _log(f"Couldn't judge some postings ({type(e).__name__}).", "warn")
        # Write applications for the best shortlisted ones (selective on purpose)
        todo = db.query("SELECT id FROM internships WHERE status='shortlisted' ORDER BY score DESC LIMIT ?",
                        (MAX_NEW_APPS_PER_RUN,))
        for r in todo:
            _safe_write(r["id"])
        ready = db.one("SELECT COUNT(*) n FROM internships WHERE status IN ('ready','needs_info')")["n"]
        db.kv_set("career_last_run", _now())
        if todo:
            msg = (f"I found {len(new)} new internship(s) and wrote {len(todo)} application(s) for the "
                   f"best fits. {ready} waiting for your OK on the Internships page.")
            announce(msg)
            notify.send("💼 StudyPilot: " + msg)
        refresh()
        shortlisted = db.one("SELECT COUNT(*) n FROM internships WHERE status IN ('ready','needs_info','shortlisted')")["n"]
        if _run_id:
            runs.finish(_run_id, "done", f"{len(new)} new posting(s) judged · {len(todo)} application(s) written · "
                                         f"{shortlisted} waiting for you")
        return {"new": len(new), "written": len(todo)}
    except Exception as e:
        if _run_id:
            runs.finish(_run_id, "fallback", f"Search stopped: {type(e).__name__}")
        raise
    finally:
        _run_id = None
        _lock.release()


def track():
    """Cheap, frequent: sent-detection, replies, follow-ups. Called from the scheduler."""
    if not profile():
        return
    for step in (_sent_check, _replies, _follow_ups):
        try:
            step()
        except Exception as e:
            print(f"[Career] {step.__name__} failed: {e}")


def tick():
    """Scheduler hook: track every ~10 min, full search once a day."""
    last_track = db.kv_get("career_last_track") or 0
    if _now() - last_track > 600:
        db.kv_set("career_last_track", _now())
        track()
    if profile() and _now() - (db.kv_get("career_last_run") or 0) > 86400:
        run()


def summary():
    """For the chat/voice assistant."""
    items = all_items()
    by = {}
    for it in items:
        by.setdefault(it["status"], []).append(f"{it['title']} at {it['company']} ({it['score'] or '?'}/100)")
    return {"has_cv": bool(profile()), "counts": {k: len(v) for k, v in by.items()},
            "waiting_for_approval": by.get("ready", [])[:5], "needs_info": by.get("needs_info", [])[:5],
            "applied": by.get("applied", [])[:5], "interviews": by.get("interview", [])[:5],
            "offers": by.get("offer", [])}
