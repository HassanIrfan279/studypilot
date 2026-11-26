"""Phone alerts. WhatsApp via Twilio (primary), Telegram as a fallback where it isn't blocked.

Message text uses simple tags: <b>bold</b> — converted to each app's own format.
"""
import re

import requests

from config import (CALLMEBOT_APIKEY, CALLMEBOT_PHONE, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                    TWILIO_WHATSAPP_FROM, WHATSAPP_TO)
from tools import telegram_tools as tg


def whatsapp_enabled():
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and WHATSAPP_TO)


def _to_whatsapp(text):
    return re.sub(r"</?b>", "*", text)  # WhatsApp bold is *text*


def send_whatsapp(text: str) -> bool:
    if not whatsapp_enabled():
        return False
    to = WHATSAPP_TO if WHATSAPP_TO.startswith("whatsapp:") else f"whatsapp:{WHATSAPP_TO}"
    try:
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), timeout=15,
            data={"From": TWILIO_WHATSAPP_FROM, "To": to, "Body": _to_whatsapp(text)[:1500]})
        if not r.ok:
            print("WhatsApp send failed:", r.status_code, r.text[:200])
        return r.ok
    except Exception as e:
        print("WhatsApp send error:", e)
        return False


def callmebot_enabled():
    return bool(CALLMEBOT_PHONE and CALLMEBOT_APIKEY)


def send_callmebot(text: str) -> bool:
    """WhatsApp via CallMeBot (free; the student activates it once from their WhatsApp)."""
    if not callmebot_enabled():
        return False
    try:
        r = requests.get("https://api.callmebot.com/whatsapp.php", timeout=20,
                         params={"phone": CALLMEBOT_PHONE, "text": _to_whatsapp(text)[:1000],
                                 "apikey": CALLMEBOT_APIKEY})
        ok = r.ok and "error" not in r.text.lower()[:300]
        if not ok:
            print("CallMeBot send failed:", r.status_code, r.text[:200])
        return ok
    except Exception as e:
        print("CallMeBot error:", e)
        return False


def send(text: str) -> bool:
    """Send to every configured channel. True if at least one delivered."""
    ok = send_callmebot(text)
    ok = send_whatsapp(text) or ok
    if tg.enabled():
        ok = tg.send(text) or ok
    return ok


def status():
    return {"whatsapp": callmebot_enabled() or whatsapp_enabled(), "telegram": tg.enabled()}
