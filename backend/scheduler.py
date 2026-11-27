"""Background loop: every SYNC_INTERVAL_SECONDS, sync Classroom and let the Coordinator react."""
import asyncio
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import db
from activity_log import log
from agents import career_agent, coach, coordinator, sync_agent, watcher
from auth import get_credentials
from config import SYNC_INTERVAL_SECONDS, TIMEZONE

_lock = threading.Lock()
_career_busy = threading.Lock()


_coach_busy = threading.Lock()


def _coach_tick():
    """Nightly review once a day (9 PM). Own thread so it never blocks Classroom sync."""
    if not _coach_busy.acquire(blocking=False):
        return
    try:
        coach.tick()
    except Exception as e:
        print(f"[Coach] tick failed: {e}")
    finally:
        _coach_busy.release()


def _career_tick():
    """Internship agent: track replies ~every 10 min, search once a day. Own thread, own lock."""
    if not _career_busy.acquire(blocking=False):
        return
    try:
        career_agent.tick()
    except Exception as e:
        print(f"[Career] tick failed: {e}")
    finally:
        _career_busy.release()


def _ago():
    last = db.kv_get("last_sync")
    if not last:
        return "never"
    mins = (datetime.now(ZoneInfo(TIMEZONE)) - datetime.fromisoformat(last)).total_seconds() / 60
    return f"{int(mins)} min ago" if mins >= 1 else "just now"


def sync_once(verbose=False):
    """One full sync + coordinator pass. Blocking — run in a thread."""
    if not _lock.acquire(blocking=False):
        return {"skipped": True}
    try:
        if verbose:
            log("Sync", "Checking Google Classroom for changes…")
        try:
            result = sync_agent.run_sync()
        except Exception as e:
            log("Sync", f"Classroom unreachable ({type(e).__name__}) — showing last sync from "
                        f"{_ago()}.", "error")
            return {"ok": False, "error": str(e)}
        n = len(result["changes"])
        if n or verbose:
            log("Sync", f"Sync done: {n} change(s) found.", "success" if n else "info")
        try:
            coordinator.handle(result)
        except Exception as e:
            log("Coordinator", f"Couldn't finish reacting to the changes ({type(e).__name__}: {e}).",
                "warn")
        watcher.tick()  # react to the student's own calendar, missed sessions
        if not db.kv_get("markers_synced"):
            coordinator.sync_deadline_markers()  # one-time: put existing deadlines in Calendar
            db.kv_set("markers_synced", True)
        return {"ok": True, "changes": n}
    except Exception as e:
        log("Sync", f"Sync step failed ({type(e).__name__}: {e}).", "warn")
        return {"ok": False, "error": str(e)}
    finally:
        _lock.release()


async def loop():
    first = True
    while True:
        try:
            logged_in = await asyncio.to_thread(get_credentials)
        except Exception as e:
            logged_in = None
            if not db.kv_get("signin_warned"):
                log("Sync", f"Google sign-in needs refreshing: {e}", "error")
                db.kv_set("signin_warned", True)
        if logged_in:
            await asyncio.to_thread(sync_once, first)
            first = False
            threading.Thread(target=_career_tick, daemon=True).start()
            threading.Thread(target=_coach_tick, daemon=True).start()
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
