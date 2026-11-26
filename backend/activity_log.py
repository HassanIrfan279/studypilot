"""Agent activity log: every step is saved to SQLite and pushed live to the browser."""
import asyncio
import json
import time

import db

_clients: list = []            # connected WebSocket clients, oldest first
_loop: asyncio.AbstractEventLoop | None = None
# Exactly ONE place speaks each announcement (several open tabs used to talk over each other):
_speaker = None                # the browser tab the student used most recently
_voice_sessions: list = []     # live Gemini voice sessions: async fn(text) that speaks it


def set_loop(loop):
    global _loop
    _loop = loop


def add_client(ws):
    if ws not in _clients:
        _clients.append(ws)


def remove_client(ws):
    global _speaker
    if ws in _clients:
        _clients.remove(ws)
    if _speaker is ws:
        _speaker = None


def mark_active(ws):
    """The student focused this tab: it becomes the one that reads announcements aloud."""
    global _speaker
    _speaker = ws


def add_voice(speak_fn):
    _voice_sessions.append(speak_fn)


def remove_voice(speak_fn):
    if speak_fn in _voice_sessions:
        _voice_sessions.remove(speak_fn)


async def _send(ws, text):
    try:
        await ws.send_text(text)
    except Exception:
        remove_client(ws)


async def _broadcast(payload: dict):
    text = json.dumps(payload)
    for ws in list(_clients):
        await _send(ws, text)


async def _announce(text: str):
    # 1) A live voice conversation is open: Gemini says it, no tab uses the robot voice
    for speak in reversed(list(_voice_sessions)):
        try:
            await speak(text)
            await _broadcast({"type": "announce", "text": text, "speak": False})
            return
        except Exception:
            remove_voice(speak)
    # 2) Otherwise only the most recently used tab speaks; the rest just show the banner
    speaker = _speaker if _speaker in _clients else (_clients[-1] if _clients else None)
    for ws in list(_clients):
        await _send(ws, json.dumps({"type": "announce", "text": text, "speak": ws is speaker}))


def _run(coro):
    """Schedule a coroutine on the server loop from any thread."""
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is _loop:
        _loop.create_task(coro)
    else:
        asyncio.run_coroutine_threadsafe(coro, _loop)


def push(payload: dict):
    """Send a message to all browsers. Safe to call from any thread."""
    if _loop:
        _run(_broadcast(payload))


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
    if _loop:
        _run(_announce(text))


def refresh():
    """Tell the UI that data changed and it should reload."""
    push({"type": "refresh"})


def recent(limit=100):
    rows = db.query("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))
    return list(reversed(rows))
