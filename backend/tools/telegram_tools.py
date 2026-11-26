"""Telegram alerts: the agent messages the student's phone.
Setup: create a bot with @BotFather, put TELEGRAM_BOT_TOKEN in .env, press Start in the bot."""
import requests

import db
from config import TELEGRAM_BOT_TOKEN

API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def enabled():
    return bool(TELEGRAM_BOT_TOKEN)


def chat_id():
    """The student's chat with the bot. Found automatically after they press Start."""
    cid = db.kv_get("telegram_chat_id")
    if cid or not enabled():
        return cid
    try:
        updates = requests.get(f"{API}/getUpdates", timeout=10).json().get("result", [])
    except Exception:
        return None
    for u in reversed(updates):
        chat = (u.get("message") or u.get("my_chat_member") or {}).get("chat")
        if chat and chat.get("type") == "private":
            db.kv_set("telegram_chat_id", chat["id"])
            return chat["id"]
    return None


def send(text: str) -> bool:
    cid = chat_id()
    if not cid:
        return False
    try:
        r = requests.post(f"{API}/sendMessage", timeout=10,
                          json={"chat_id": cid, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True})
        return r.ok
    except Exception:
        return False


def status():
    return {"configured": enabled(), "connected": bool(chat_id())}
