"""Tutor tools: lecture analysis, practice quizzes, prep packs, panic mode, readiness, daily brief.
Every Gemini result is cached in SQLite so the same file is never analyzed twice."""
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel

import db
import gemini
from activity_log import log
from config import TIMEZONE
from tools.drive_tools import fetch_lecture
from tools.youtube_tools import find_videos

TUTOR_SYSTEM = ("You are StudyPilot's tutor for Pakistani university CS students. Explain simply, "
                "use short sentences and everyday examples. Stay grounded ONLY in the provided "
                "lecture material. Never write graded assignments for the student.")


# ---------- schemas (Gemini structured output) ----------
class Concept(BaseModel):
    name: str
    simple_explanation: str


class LectureAnalysis(BaseModel):
    title: str
    summary: str
    key_concepts: list[Concept]
    likely_exam_points: list[str]
    youtube_search_topics: list[str]
    difficulty: int
    estimated_study_hours: float


class MCQ(BaseModel):
    question: str
    options: list[str]
    correct_index: int
    explanation: str


class Quiz(BaseModel):
    questions: list[MCQ]


class CramTopic(BaseModel):
    topic: str
    must_know: list[str]


class CramSheet(BaseModel):
    headline: str
    top_topics: list[CramTopic]
    last_minute_tips: list[str]
    rapid_quiz: list[MCQ]


class FoundDeadline(BaseModel):
    title: str
    kind: str          # "quiz" or "assignment"
    due_date: str      # YYYY-MM-DD or "" if unknown
    due_time: str      # HH:MM 24h or ""
    ambiguous: bool
    status: str        # "active" or "cancelled"
    evidence: str      # short quote from the announcement that supports this


class FoundDeadlines(BaseModel):
    deadlines: list[FoundDeadline]


class UrduText(BaseModel):
    urdu: str


# ---------- helpers ----------
def now_local():
    return datetime.now(ZoneInfo(TIMEZONE))


def course_name(course_id):
    row = db.one("SELECT name FROM courses WHERE id=?", (course_id,))
    return row["name"] if row else "Course"


def get_item(item_id):
    return db.one("SELECT * FROM items WHERE id=?", (item_id,))


def days_left(due_iso):
    if not due_iso:
        return None
    due = datetime.fromisoformat(due_iso)
    return (due - datetime.now(timezone.utc)).total_seconds() / 86400


# ---------- lecture analysis ----------
def analyze_lecture(file_id):
    cached = db.cache_get(f"analysis:{file_id}")
    if cached:
        return cached
    mat = db.one("SELECT * FROM materials WHERE file_id=?", (file_id,)) or {}
    lec = fetch_lecture(file_id)
    log("Tutor", f"Reading lecture '{lec['name']}' with Gemini…")
    prompt = ("Analyze this university lecture. Give: a clear summary (5-8 sentences), the key "
              "concepts each with a very simple explanation a struggling student understands, the "
              "points most likely to appear in a quiz/exam, 2-4 short YouTube search topics, "
              "difficulty 1-5, and realistic study hours needed (0.5-6).")
    if lec["kind"] == "text":
        parts = [f"LECTURE '{lec['name']}':\n{lec['text'][:60000]}"]
    else:
        parts = [gemini.file_part(lec["data"], lec["mime"])]
    result = gemini.generate_json(prompt, LectureAnalysis, parts=parts, system=TUTOR_SYSTEM)
    result["file_id"] = file_id
    result["file_name"] = lec["name"]
    result["course_id"] = mat.get("course_id")
    db.cache_set(f"analysis:{file_id}", result)
    log("Tutor", f"Lecture '{lec['name']}' analyzed: {len(result['key_concepts'])} concepts, "
                 f"difficulty {result['difficulty']}/5, ~{result['estimated_study_hours']}h to study.",
        "success")
    return result


def explain_in_urdu(text):
    key = "urdu:" + hashlib.sha1(text.encode()).hexdigest()
    cached = db.cache_get(key)
    if cached:
        return cached
    out = gemini.generate_json(
        "Translate and explain this in simple, natural Urdu (Urdu script) the way a friendly senior "
        "student would. Keep technical terms in English inside the Urdu sentence.\n\n" + text,
        UrduText)["urdu"]
    db.cache_set(key, out)
    return out


# ---------- which lectures belong to an assessment ----------
def lectures_for_assessment(assessment_id, limit=4):
    item = get_item(assessment_id)
    if not item:
        return []
    attached = db.query("SELECT file_id FROM materials WHERE item_id=?", (assessment_id,))
    # Course lectures = files NOT attached to some other assignment
    course = db.query("SELECT file_id, title, created FROM materials WHERE course_id=? AND "
                      "(item_id IS NULL OR item_id=?) ORDER BY created DESC",
                      (item["course_id"], assessment_id))

    def words(text):
        return set(re.findall(r"[a-z]+|\d+", (text or "").lower().replace("_", " "))) - STOP

    want = words(item["title"] + " " + (item["description"] or ""))
    # Best title match first ("Quiz - Chapter 3" -> "Chapter_3_v9.0.pptx"), then newest
    course.sort(key=lambda r: -len(want & words(r["title"])))
    ids = [r["file_id"] for r in attached]
    best = course[0] if course else None
    if best and want & words(best["title"]) and len(want & words(best["title"])) >= 2:
        # a strong match (e.g. same chapter number): focus on it
        course = [best] + [r for r in course[1:] if len(want & words(r["title"])) >= 2]
    for r in course:
        if r["file_id"] not in ids:
            ids.append(r["file_id"])
    return ids[:limit]


STOP = {"quiz", "the", "a", "of", "and", "in", "on", "for", "to", "v", "pdf", "pptx", "docx",
        "found", "class", "announcement", "test", "assignment", "lecture", "slides", "recent"}


def _analyses(file_ids):
    out = []
    for fid in file_ids:
        try:
            out.append(analyze_lecture(fid))
        except Exception as e:
            log("Tutor", f"Skipped a lecture file: {e}", "warn")
    return out


def _material_text(analyses):
    chunks = []
    for a in analyses:
        concepts = "\n".join(f"- {c['name']}: {c['simple_explanation']}" for c in a["key_concepts"])
        points = "\n".join(f"- {p}" for p in a["likely_exam_points"])
        chunks.append(f"## {a['title']}\n{a['summary']}\nConcepts:\n{concepts}\nExam points:\n{points}")
    return "\n\n".join(chunks)


# ---------- quizzes ----------
def generate_practice_quiz(file_ids, n=8):
    key = f"quiz:{','.join(sorted(file_ids))}:{n}"
    cached = db.cache_get(key)
    if cached:
        return cached
    analyses = _analyses(file_ids)
    if not analyses:
        return {"questions": []}
    log("Tutor", f"Writing {n} practice questions from {len(analyses)} lecture(s)…")
    quiz = gemini.generate_json(
        f"Write exactly {n} multiple-choice questions (4 options each, one correct) that test "
        "understanding of this lecture material only. Mix easy and tricky. Explain each answer "
        "in one sentence.\n\n" + _material_text(analyses), Quiz, system=TUTOR_SYSTEM)
    db.cache_set(key, quiz)
    return quiz


def fresh_questions(assessment_id, n=8, purpose="retake"):
    """Brand-new MCQs every call: never repeats a question already asked for this assessment,
    and targets the concepts behind the student's previous wrong answers."""
    analyses = _analyses(lectures_for_assessment(assessment_id))
    if not analyses:
        return {"questions": []}
    asked = db.kv_get(f"asked:{assessment_id}") or []
    pack = db.cache_get(f"prep:{assessment_id}")
    if pack:
        asked += [q["question"] for q in pack["quiz"]["questions"]]
    wrong = []
    for r in db.query("SELECT wrong FROM quiz_results WHERE assessment_id=? ORDER BY id DESC LIMIT 3",
                      (assessment_id,)):
        try:
            wrong += json.loads(r["wrong"] or "[]")
        except ValueError:
            pass
    focus = ("\nThe student previously got these WRONG — test the same underlying concepts "
             "again but with different questions, numbers and angles:\n" + "\n".join(f"- {w}" for w in wrong[:8])
             ) if wrong else ""
    avoid = "\nDo NOT reuse or rephrase any of these already-asked questions:\n" + \
            "\n".join(f"- {a}" for a in asked[-40:]) if asked else ""
    style = ("Short check that the student really studied this session: 3 questions that need "
             "understanding, not memorization." if purpose == "check" else
             "A fresh practice quiz, harder than a recall test: include 'why' and applied questions.")
    quiz = gemini.generate_json(
        f"{style} Write exactly {n} multiple-choice questions (4 options, one correct) with a "
        f"one-sentence explanation each, grounded only in this material.{focus}{avoid}\n\n"
        + _material_text(analyses), Quiz, system=TUTOR_SYSTEM)
    db.kv_set(f"asked:{assessment_id}", (asked + [q["question"] for q in quiz["questions"]])[-120:])
    return quiz


_next_locks: dict = {}


def _next_lock(assessment_id):
    return _next_locks.setdefault(assessment_id, threading.Lock())


def prepare_next_quiz(assessment_id):
    """After every attempt: write the NEXT quiz in the background (new questions, aimed at what
    was just missed) and put it in the prep pack and cram sheet, so reopening never shows the
    same questions again and 'Retake' is instant."""
    with _next_lock(assessment_id):
        try:
            quiz = fresh_questions(assessment_id, 8, "retake")
        except Exception as e:
            log("Tutor", f"Couldn't pre-write the next quiz ({type(e).__name__}); it will be written on Retake.", "warn")
            return
        if not quiz.get("questions"):
            return
        db.kv_set(f"next_quiz:{assessment_id}", quiz)
        pack = db.cache_get(f"prep:{assessment_id}")
        if pack:
            pack["quiz"] = quiz
            db.cache_set(f"prep:{assessment_id}", pack)
        sheet = db.cache_get(f"panic:{assessment_id}")
        if sheet:
            sheet["rapid_quiz"] = quiz["questions"][:5]
            db.cache_set(f"panic:{assessment_id}", sheet)
    log("Tutor", "Next practice quiz is ready — new questions on what you just missed.", "success")


def take_next_quiz(assessment_id, n=8):
    """Retake button: use the pre-written quiz if it's ready, else write one now."""
    with _next_lock(assessment_id):  # waits if the background writer is still busy
        quiz = db.kv_get(f"next_quiz:{assessment_id}")
        if quiz and quiz.get("questions"):
            db.execute("DELETE FROM kv WHERE key=?", (f"next_quiz:{assessment_id}",))
            return {"questions": quiz["questions"][:n]}
        return fresh_questions(assessment_id, n, "retake")


def save_quiz_result(assessment_id, score, wrong=None):
    db.execute("INSERT INTO quiz_results(assessment_id, score, ts, wrong) VALUES (?,?,?,?)",
               (assessment_id, score, datetime.now().timestamp(), json.dumps(wrong or [])))
    log("Tutor", f"Practice quiz scored {round(score * 100)}% — readiness updated.", "success")


# ---------- prep pack ----------
def build_prep_pack(assessment_id, refresh=False):
    key = f"prep:{assessment_id}"
    if not refresh:
        cached = db.cache_get(key)
        if cached:
            return cached
    item = get_item(assessment_id)
    if not item:
        return None
    file_ids = lectures_for_assessment(assessment_id)
    log("Tutor", f"Building prep pack for '{item['title']}' from {len(file_ids)} lecture(s).")
    analyses = _analyses(file_ids)
    quiz = {"questions": []}
    if analyses:
        attempted = db.one("SELECT 1 FROM quiz_results WHERE assessment_id=?", (assessment_id,))
        quiz = (db.kv_get(f"next_quiz:{assessment_id}")
                or (fresh_questions(assessment_id, 8, "retake") if attempted else None)
                or generate_practice_quiz(file_ids))  # first time only: the original quiz
    topics = []
    for a in analyses:
        topics.extend(a.get("youtube_search_topics", [])[:1])
    videos = [{"topic": t, "videos": find_videos(t)} for t in topics[:3]]
    pack = {"assessment": item, "course_name": course_name(item["course_id"]),
            "lectures": analyses, "quiz": quiz, "videos": videos}
    db.cache_set(key, pack)
    log("Tutor", f"Prep pack ready for '{item['title']}'.", "success")
    return pack


# ---------- panic mode ----------
def panic_mode(assessment_id, minutes_available=120):
    item = get_item(assessment_id)
    if not item:
        return None
    key = f"panic:{assessment_id}"
    cached = db.cache_get(key, max_age=3600)
    if cached:
        return cached
    log("Coordinator", f"🚨 Panic mode for '{item['title']}' — {minutes_available} min available.",
        "warn")
    analyses = _analyses(lectures_for_assessment(assessment_id))
    sheet = gemini.generate_json(
        f"The student has a '{item['title']}' in {minutes_available} minutes and is unprepared. "
        "Build a 20-minute cram sheet: the 3-5 highest-priority topics with must-know bullet "
        "points, a few last-minute tips, and exactly 5 rapid MCQs.\n\n" + _material_text(analyses),
        CramSheet, system=TUTOR_SYSTEM)
    sheet["assessment"] = item
    db.cache_set(key, sheet)
    log("Tutor", "Cram sheet + 5-question rapid quiz ready.", "success")
    return sheet


# ---------- readiness ----------
def readiness(assessment_id):
    planned = db.one("SELECT COUNT(*) n FROM sessions WHERE assessment_id=?", (assessment_id,))["n"]
    done = db.one("SELECT COUNT(*) n FROM sessions WHERE assessment_id=? AND done=1",
                  (assessment_id,))["n"]
    best = db.one("SELECT MAX(score) s FROM quiz_results WHERE assessment_id=?", (assessment_id,))["s"]
    session_part = (done / planned) if planned else 0
    quiz_part = best or 0
    score = round(100 * (0.5 * session_part + 0.5 * quiz_part))
    return {"score": score, "sessions_done": done, "sessions_planned": planned,
            "best_quiz": round(100 * quiz_part)}


# ---------- hidden deadlines in announcements ----------
def extract_course_deadlines(course, announcements, tracked=None):
    """Read ALL recent announcements of one course together (oldest first) and return the
    CURRENT deadlines with a status. `tracked` = deadlines we already know about, so Gemini
    updates them by the same title instead of inventing new ones."""
    anns = [a for a in announcements if len(a["text"].strip()) >= 10]
    if not anns:
        return []
    anns.sort(key=lambda a: a["created"] or a["update_time"])
    feed = "\n\n".join(
        f"[Posted {datetime.fromisoformat(a['created'].replace('Z', '+00:00')).astimezone(now_local().tzinfo):%A %Y-%m-%d %H:%M}]\n{a['text'][:1500]}"
        for a in anns)
    known = "\n".join(f"- {t['title']} ({t['kind']}), due {t['due'] or 'unknown'}"
                      for t in (tracked or [])) or "- none"
    key = "hidden:" + hashlib.sha1((course + feed + known).encode()).hexdigest()
    cached = db.cache_get(key)
    if cached is not None:
        return cached
    out = gemini.generate_json(
        f"Today is {now_local():%A %Y-%m-%d}. Below are a teacher's announcements for the course "
        f"'{course}', oldest first, and the deadlines we ALREADY TRACK for this course.\n"
        "Return the full current list of quiz / test / viva / exam / submission deadlines:\n"
        "1. Every already-tracked deadline must appear again with EXACTLY the same title.\n"
        "2. Later announcements update earlier ones. If one is postponed, give the new date. If "
        "the new date is vague (e.g. 'week after next'), set ambiguous=true.\n"
        "3. status='cancelled' ONLY if an announcement clearly cancels THAT specific item "
        "(e.g. 'quiz cancelled' cancels a quiz, never a viva or a different item). Otherwise "
        "status='active'.\n"
        "4. Add new deadlines found in the text with a short stable title like 'Quiz - Chapter 3'.\n"
        "5. Resolve relative dates ('upcoming Monday') from the date the announcement was posted. "
        "For an in-class quiz with no time use 09:00. kind='quiz' for quiz/test/viva/exam, else "
        "'assignment'. Put a short supporting quote in evidence.\n\n"
        f"ALREADY TRACKED:\n{known}\n\nANNOUNCEMENTS:\n{feed}",
        FoundDeadlines)
    found = out["deadlines"]
    db.cache_set(key, found)
    return found


# ---------- daily brief ----------
def upcoming_items(days=14):
    rows = db.query("SELECT * FROM items WHERE active=1 ORDER BY due IS NULL, due")
    out = []
    month_ago = (datetime.now(timezone.utc).timestamp() - 30 * 86400)
    for r in rows:
        dl = days_left(r["due"])
        if dl is None:
            # undated work only matters if the teacher touched it recently
            try:
                fresh = datetime.fromisoformat(r["update_time"].replace("Z", "+00:00")).timestamp() > month_ago
            except Exception:
                fresh = False
            if not fresh:
                continue
        if dl is None or -0.5 <= dl <= days:
            r["days_left"] = dl
            r["course_name"] = course_name(r["course_id"])
            r["readiness"] = readiness(r["id"])
            out.append(r)
    return out


def daily_brief(refresh=False):
    if not refresh:
        cached = db.cache_get("brief", max_age=1800)
        if cached:
            return cached
    items = upcoming_items(7)
    changes = db.query("SELECT message FROM activity WHERE agent IN ('Sync','Planner') "
                       "AND level IN ('warn','success') ORDER BY id DESC LIMIT 8")
    today = now_local().date().isoformat()
    sessions = db.query("SELECT title, start FROM sessions WHERE substr(start,1,10)=? AND done=0",
                        (today,))
    facts = "\n".join(
        f"- {i['course_name']}: {i['title']} ({i['kind']}) due in "
        f"{'?' if i['days_left'] is None else round(i['days_left'], 1)} days, readiness "
        f"{i['readiness']['score']}%" for i in items) or "- nothing due this week"
    text = gemini.generate_text(
        f"Today is {now_local():%A %d %B}. Write the student's daily brief in 3 short parts: "
        "'Due soon', 'What changed', 'Study today'. Max 90 words, friendly, use the data only.\n\n"
        f"DEADLINES:\n{facts}\n\nRECENT CHANGES:\n" +
        "\n".join(f"- {c['message']}" for c in changes) +
        "\n\nSTUDY SESSIONS TODAY:\n" + ("\n".join(f"- {s['title']} at {s['start'][11:16]}"
                                                     for s in sessions) or "- none"))
    brief = {"text": text, "generated": now_local().isoformat()}
    db.cache_set("brief", brief)
    return brief
