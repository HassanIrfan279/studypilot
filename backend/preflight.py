"""Pre-flight check: test every service the demo depends on, in parallel, before going on stage.

Each check returns {name, ok, ms, detail, fix}. Nothing here changes the student's data:
Calendar/Drive/Gmail/Classroom are read, Gemini gets a one-word prompt, Live opens and closes.
"""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from google.genai import types

import db
import gemini
import google_clients as g
from auth import get_credentials
from config import (DEMO_MODE, LIVE_MODEL_CHAIN, MODEL_CHAIN, SYNC_INTERVAL_SECONDS, TIMEZONE,
                    YOUTUBE_API_KEY)
from tools import notify

TIMEOUT = 25  # seconds per check


def _token():
    creds = get_credentials()
    if not creds:
        raise RuntimeError("Not signed in")
    me = g.with_retry(lambda: g.oauth2().userinfo().get().execute(), attempts=2)
    missing = db.kv_get("missing_scopes") or []
    if missing:
        raise RuntimeError(f"Missing permissions: {', '.join(missing)}")
    issued = db.kv_get("token_issued")
    if not issued:
        row = db.one("SELECT ts FROM activity WHERE message LIKE '%Signed in with Google%' ORDER BY id DESC")
        issued = row and row["ts"]
    who = f"Signed in as {me.get('name') or me.get('email')}"
    if issued:
        days = (time.time() - issued) / 86400
        expires = datetime.fromtimestamp(issued + 7 * 86400, ZoneInfo(TIMEZONE)).strftime("%a %d %b %H:%M")
        if days > 5:
            raise RuntimeError(f"{who}, but Google will expire this sign-in on {expires}. Sign in again now.")
        who += f" · sign-in valid until {expires}"
    return who


def _classroom():
    svc = g.classroom()
    r = g.with_retry(lambda: svc.courses().list(studentId="me", courseStates=["ACTIVE"],
                                                 pageSize=20).execute(), attempts=2)
    return f"{len(r.get('courses', []))} active course(s)"


def _calendar():
    svc = g.calendar()
    now = datetime.now(timezone.utc).isoformat()
    r = g.with_retry(lambda: svc.events().list(
        calendarId="primary", timeMin=now, maxResults=50, singleEvents=True,
        privateExtendedProperty="studypilot=true").execute(), attempts=2)
    return f"{len(r.get('items', []))} upcoming StudyPilot event(s)"


def _drive():
    svc = g.drive()
    about = g.with_retry(lambda: svc.about().get(fields="user").execute(), attempts=2)
    folder = db.kv_get("folder:root:StudyPilot")
    return "Drive reachable" + (", StudyPilot folder exists" if folder else "")


def _gmail():
    svc = g._service("gmail", "v1")
    p = g.with_retry(lambda: svc.users().getProfile(userId="me").execute(), attempts=2)
    return f"{p.get('messagesTotal', 0)} messages, read-only"


def _gemini_model(model):
    def check():
        cfg = types.GenerateContentConfig(temperature=0, max_output_tokens=5,
                                          http_options=types.HttpOptions(timeout=20_000))
        r = gemini.client.models.generate_content(model=model, contents="Reply with: ok", config=cfg)
        return f"answered “{(r.text or '').strip()[:20]}”"
    return check


async def _live(model):
    cfg = types.LiveConnectConfig(response_modalities=["AUDIO"])
    cm = gemini.client.aio.live.connect(model=model, config=cfg)
    await asyncio.wait_for(cm.__aenter__(), timeout=15)
    try:
        return "voice session opened"
    finally:
        try:
            await cm.__aexit__(None, None, None)
        except Exception:
            pass


def _live_check():
    errors = []
    for i, model in enumerate(LIVE_MODEL_CHAIN):
        try:
            msg = asyncio.run(_live(model))
            return (f"{model}: {msg}" if i == 0 else
                    f"main voice model down; backup {model} works")
        except Exception as e:
            errors.append(f"{model}: {type(e).__name__}")
    raise RuntimeError("; ".join(errors))


def _youtube():
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY missing")
    r = requests.get("https://www.googleapis.com/youtube/v3/search", timeout=10, params={
        "part": "id", "q": "binary search", "type": "video", "maxResults": 1, "key": YOUTUBE_API_KEY})
    r.raise_for_status()
    return "search works"


def _alerts():
    s = notify.status()
    on = [k for k, v in s.items() if v]
    if not on:
        raise RuntimeError("No phone alert channel configured")
    return "configured: " + ", ".join(on) + " (use “Send test alert” to really send one)"


def _sync():
    last = db.kv_get("last_sync")
    if not last:
        raise RuntimeError("Never synced")
    age = (datetime.now(ZoneInfo(TIMEZONE)) - datetime.fromisoformat(last)).total_seconds()
    if age > max(120, SYNC_INTERVAL_SECONDS * 6):
        raise RuntimeError(f"Last sync {int(age // 60)} min ago — background sync looks stuck")
    mode = "DEMO_MODE on (10 s)" if DEMO_MODE else f"every {SYNC_INTERVAL_SECONDS}s (turn DEMO_MODE on)"
    return f"last sync {int(age)}s ago · {mode}"


def _cache():
    upcoming = db.query("SELECT id FROM items WHERE active=1 AND due > ?",
                        (datetime.now(timezone.utc).isoformat(),))
    packs = sum(1 for r in upcoming if db.cache_get(f"prep:{r['id']}"))
    if upcoming and packs < len(upcoming):
        raise RuntimeError(f"{packs}/{len(upcoming)} prep packs pre-built — run Warm up")
    return f"{packs}/{len(upcoming)} prep packs ready (instant on stage)"


def _drafts():
    from agents import career_agent
    if not career_agent.has_compose():
        raise RuntimeError("Gmail drafts permission not granted (internship applications and exam-clash emails)")
    return "can create Gmail drafts (never sends)"


def _career():
    from agents import career_agent
    p = career_agent.profile()
    if not p:
        raise RuntimeError("No CV yet")
    items = career_agent.all_items()
    waiting = sum(1 for i in items if i["status"] in ("ready", "needs_info"))
    return f"CV ready ({p.get('name') or 'you'}) · {len(items)} posting(s) tracked · {waiting} waiting for you"


def _coach():
    from agents import coach
    last = db.kv_get("last_review")
    h = coach.habit_stats()
    when = datetime.fromtimestamp(last["ts"], ZoneInfo(TIMEZONE)).strftime("%a %H:%M") if last else "not yet"
    return (f"nightly review at {coach.REVIEW_HOUR}:00 (last: {when}) · habits "
            + ("learning" if h["learning"] else "learned") + f" · {len(coach.reviews())} review quiz(zes) scheduled")


def _mcp():
    from agents import brain
    decls = brain.mcp_discover()
    return f"{len(decls)} agent tools served at /mcp/ (Streamable HTTP), discovered via tools/list"


FIXES = {
    "MCP server": "Restart the backend; the agents fall back to calling tools directly meanwhile.",
    "Google sign-in": "Click Sign in again (testing-mode Google tokens expire after 7 days).",
    "Classroom": "Check the internet connection, then sign in again.",
    "Google Calendar": "Check the internet connection, then sign in again.",
    "Google Drive": "Sign in again and tick the Drive boxes.",
    "Gmail": "Enable the Gmail API in Google Cloud, then sign in again.",
    "Voice (Gemini Live)": "Use the text chat box on stage instead of voice.",
    "YouTube": "Check YOUTUBE_API_KEY; videos are optional in the demo.",
    "Phone alerts": "Add DISCORD_WEBHOOK_URL to the environment.",
    "Background sync": "Restart the backend.",
    "Pre-built content": "Click Warm up and wait for “All set”.",
    "Gmail drafts": "Sign in again and tick the Gmail box.",
    "Internship agent": "Open Internships and upload or build your CV.",
    "Coach (nightly review)": "Restart the backend.",
}


def run_all():
    checks = [("Google sign-in", _token), ("Classroom", _classroom), ("Google Calendar", _calendar),
              ("Google Drive", _drive), ("Gmail", _gmail)]
    checks += [(f"Gemini · {m}" + (" (main)" if i == 0 else " (backup)"), _gemini_model(m))
               for i, m in enumerate(MODEL_CHAIN[:3])]
    checks += [("Voice (Gemini Live)", _live_check), ("YouTube", _youtube), ("Phone alerts", _alerts),
               ("Background sync", _sync), ("Pre-built content", _cache), ("Gmail drafts", _drafts),
               ("Internship agent", _career), ("Coach (nightly review)", _coach), ("MCP server", _mcp)]
    out = []
    pool = ThreadPoolExecutor(max_workers=len(checks))
    futures = [(name, pool.submit(_timed, fn)) for name, fn in checks]
    deadline = time.time() + TIMEOUT
    for name, fut in futures:
        try:
            ok, ms, detail = fut.result(timeout=max(0.1, deadline - time.time()))
        except FutTimeout:
            ok, ms, detail = False, TIMEOUT * 1000, f"no answer within {TIMEOUT}s"
        fix = "" if ok else FIXES.get(name, "Try again; the app falls back to a backup model.")
        out.append({"name": name, "ok": ok, "ms": ms, "detail": detail, "fix": fix})
    pool.shutdown(wait=False, cancel_futures=True)  # never let one slow check hold the page
    gem = [c for c in out if c["name"].startswith("Gemini")]
    if gem and not gem[0]["ok"] and any(c["ok"] for c in gem[1:]):
        gem[0]["fix"] = "Fine for the demo: StudyPilot switches to the working backup automatically."
    return {"ok": all(c["ok"] for c in out), "checked_at": datetime.now(ZoneInfo(TIMEZONE)).isoformat(),
            "checks": out}


def _timed(fn):
    """(ok, milliseconds, detail-or-error)"""
    t = time.time()
    try:
        detail = fn()
        return True, int((time.time() - t) * 1000), detail
    except Exception as e:
        return False, int((time.time() - t) * 1000), f"{type(e).__name__}: {str(e)[:200]}"
