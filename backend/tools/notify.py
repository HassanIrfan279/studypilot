"""Phone alerts. WhatsApp via Twilio (primary), Telegram as a fallback where it isn't blocked.

Message text uses simple tags: <b>bold</b> — converted to each app's own format.
"""
import re

import requests

from config import (CALLMEBOT_APIKEY, CALLMEBOT_PHONE, NTFY_TOPIC, TWILIO_ACCOUNT_SID,
                    TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM, WA_PHONE_NUMBER_ID, WA_TO, WA_TOKEN,
                    WHATSAPP_TO)
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


def meta_enabled():
    return bool(WA_TOKEN and WA_PHONE_NUMBER_ID and WA_TO)


def send_meta_whatsapp(text: str) -> bool:
    """WhatsApp via Meta's official WhatsApp Cloud API (free test number).
    Free-form text works within 24h after the student messages the test number."""
    if not meta_enabled():
        return False
    try:
        r = requests.post(f"https://graph.facebook.com/v21.0/{WA_PHONE_NUMBER_ID}/messages",
                          headers={"Authorization": f"Bearer {WA_TOKEN}"}, timeout=15,
                          json={"messaging_product": "whatsapp", "to": WA_TO.lstrip("+"),
                                "type": "text", "text": {"body": _to_whatsapp(text)[:4000]}})
        if not r.ok:
            print("Meta WhatsApp send failed:", r.status_code, r.text[:300])
        return r.ok
    except Exception as e:
        print("Meta WhatsApp error:", e)
        return False


def ntfy_enabled():
    return bool(NTFY_TOPIC)


def send_ntfy(text: str) -> bool:
    """Phone push notification via the free ntfy app (subscribe to the same topic)."""
    if not ntfy_enabled():
        return False
    try:
        plain = re.sub(r"</?b>", "", text)
        title, _, body = plain.partition("\n")
        r = requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=(body or title).encode("utf-8"),
                          headers={"Title": title.encode("utf-8"), "Tags": "books",
                                   "Priority": "high"}, timeout=10)
        return r.ok
    except Exception as e:
        print("ntfy error:", e)
        return False


def send(text: str) -> bool:
    """Send to every configured channel. True if at least one delivered."""
    ok = send_meta_whatsapp(text)
    ok = send_ntfy(text) or ok
    ok = send_callmebot(text) or ok
    ok = send_whatsapp(text) or ok
    if tg.enabled():
        ok = tg.send(text) or ok
    return ok


def status():
    return {"whatsapp": meta_enabled() or callmebot_enabled() or whatsapp_enabled(),
            "push": ntfy_enabled(), "telegram": tg.enabled()}
