"""Agent activity log: every step is saved to SQLite and pushed live to the browser."""
import asyncio
import json
import time

import db

_clients: set = set()          # connected WebSocket clients
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop):
    global _loop
    _loop = loop


def add_client(ws):
    _clients.add(ws)


def remove_client(ws):
    _clients.discard(ws)


async def _broadcast(payload: dict):
    text = json.dumps(payload)
    for ws in list(_clients):
        try:
            await ws.send_text(text)
        except Exception:
            _clients.discard(ws)


def push(payload: dict):
    """Send a message to all browsers. Safe to call from any thread."""
    if not _loop:
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is _loop:
        _loop.create_task(_broadcast(payload))
    else:
        asyncio.run_coroutine_threadsafe(_broadcast(payload), _loop)


def log(agent: str, message: str, level: str = "info"):
    """agent: Coordinator / Sync / Tutor / Planner / Voice. level: info | success | warn | error"""
    ts = time.time()
    entry_id = db.execute("INSERT INTO activity(ts, agent, message, level) VALUES (?,?,?,?)",
                          (ts, agent, message, level))
    print(f"[{agent}] {message}")
    push({"type": "log", "entry": {"id": entry_id, "ts": ts, "agent": agent,
                                    "message": message, "level": level}})


def announce(text: str):
    """'Agent speaks first' — the browser reads this out loud."""
    log("Coordinator", f"🔊 {text}", "success")
    push({"type": "announce", "text": text})


def refresh():
    """Tell the UI that data changed and it should reload."""
    push({"type": "refresh"})


def recent(limit=100):
    rows = db.query("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))
    return list(reversed(rows))
