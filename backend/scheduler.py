"""Background loop: every SYNC_INTERVAL_SECONDS, sync Classroom and let the Coordinator react."""
import asyncio
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import db
from activity_log import log
from agents import coordinator, sync_agent
from auth import get_credentials
from config import SYNC_INTERVAL_SECONDS, TIMEZONE

_lock = threading.Lock()


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
        result = sync_agent.run_sync()
        n = len(result["changes"])
        if n or verbose:
            log("Sync", f"Sync done: {n} change(s) found.", "success" if n else "info")
        coordinator.handle(result)
        return {"ok": True, "changes": n}
    except Exception as e:
        log("Sync", f"Classroom unreachable ({type(e).__name__}) — showing last sync from {_ago()}.",
            "error")
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
            log("Sync", f"Google sign-in needs refreshing: {e}", "error")
        if logged_in:
            await asyncio.to_thread(sync_once, first)
            first = False
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
