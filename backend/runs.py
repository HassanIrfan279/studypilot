"""Agent runs: one run per trigger (teacher change, calendar clash, missed session, weak quiz…).
Each run records the agent's reasoning and every action, and streams live to the browser."""
import time

import db
from activity_log import log, push

db.execute("""CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, trigger TEXT, title TEXT, status TEXT,
    summary TEXT, started REAL, ended REAL, brain TEXT)""")
db.execute("""CREATE TABLE IF NOT EXISTS run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, ts REAL, kind TEXT, text TEXT)""")

# kind of step: think (Gemini's reasoning) | act (a tool call) | ok (result) | warn | ask | say


def start(trigger: str, title: str, brain: str = "gemini") -> int:
    run_id = db.execute("INSERT INTO runs(trigger, title, status, summary, started, brain) "
                        "VALUES (?,?,?,?,?,?)", (trigger, title, "running", "", time.time(), brain))
    log("Coordinator", f"▶ Agent run started: {title}")
    push({"type": "run", "run": get(run_id)})
    return run_id


def step(run_id: int, kind: str, text: str):
    if not run_id:
        return
    sid = db.execute("INSERT INTO run_steps(run_id, ts, kind, text) VALUES (?,?,?,?)",
                     (run_id, time.time(), kind, text))
    push({"type": "run_step", "run_id": run_id,
          "step": {"id": sid, "ts": time.time(), "kind": kind, "text": text}})


def finish(run_id: int, status: str = "done", summary: str = ""):
    db.execute("UPDATE runs SET status=?, summary=?, ended=? WHERE id=?",
               (status, summary, time.time(), run_id))
    push({"type": "run", "run": get(run_id)})


def get(run_id):
    r = db.one("SELECT * FROM runs WHERE id=?", (run_id,))
    if r:
        r["steps"] = db.query("SELECT id, ts, kind, text FROM run_steps WHERE run_id=? ORDER BY id",
                              (run_id,))
    return r


def recent(limit=12):
    ids = [r["id"] for r in db.query("SELECT id FROM runs ORDER BY id DESC LIMIT ?", (limit,))]
    return [get(i) for i in ids]
