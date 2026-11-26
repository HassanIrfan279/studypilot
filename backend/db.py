"""Tiny SQLite layer. Every table is simple; JSON blobs are stored as text."""
import json
import sqlite3
import threading
import time

from config import DB_PATH

_lock = threading.RLock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS courses (id TEXT PRIMARY KEY, name TEXT, section TEXT, color INTEGER);
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY, course_id TEXT, kind TEXT, title TEXT, description TEXT,
    due TEXT, update_time TEXT, link TEXT, source TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS materials (
    file_id TEXT PRIMARY KEY, course_id TEXT, title TEXT, mime TEXT, link TEXT,
    item_id TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, data TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS quiz_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT, assessment_id TEXT, score REAL, ts REAL);
CREATE TABLE IF NOT EXISTS sessions (
    event_id TEXT PRIMARY KEY, assessment_id TEXT, title TEXT, start TEXT, end TEXT,
    done INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, agent TEXT, message TEXT, level TEXT);
"""

with _lock:
    _conn.executescript(SCHEMA)
    # small migrations for columns added later
    for table, col, typ in [("quiz_results", "wrong", "TEXT"), ("sessions", "focus", "TEXT")]:
        cols = [r[1] for r in _conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in cols:
            _conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
    _conn.commit()


def query(sql, params=()):
    with _lock:
        return [dict(r) for r in _conn.execute(sql, params).fetchall()]


def one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    with _lock:
        cur = _conn.execute(sql, params)
        _conn.commit()
        return cur.lastrowid


# ---- key/value + cache helpers ----
def kv_get(key, default=None):
    row = one("SELECT value FROM kv WHERE key=?", (key,))
    return json.loads(row["value"]) if row else default


def kv_set(key, value):
    execute("INSERT OR REPLACE INTO kv(key, value) VALUES (?, ?)", (key, json.dumps(value)))


def cache_get(key, max_age=None):
    row = one("SELECT data, ts FROM cache WHERE key=?", (key,))
    if not row:
        return None
    if max_age is not None and time.time() - row["ts"] > max_age:
        return None
    return json.loads(row["data"])


def cache_set(key, data):
    execute("INSERT OR REPLACE INTO cache(key, data, ts) VALUES (?, ?, ?)",
            (key, json.dumps(data), time.time()))


def cache_delete(key):
    execute("DELETE FROM cache WHERE key=?", (key,))
