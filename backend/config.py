"""Loads settings from backend/.env so nothing is hard-coded."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# Allow OAuth over plain http on localhost and tolerate Google returning extra scopes
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"
# If the main model is overloaded (503/429) we automatically try these, in order
FALLBACK_MODELS = [m.strip() for m in os.getenv(
    "GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-flash-lite-latest").split(",")
    if m.strip()]
MODEL_CHAIN = [GEMINI_MODEL] + [m for m in FALLBACK_MODELS if m != GEMINI_MODEL]
GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL") or "gemini-3.8-live"
LIVE_MODEL_CHAIN = [GEMINI_LIVE_MODEL] + [m.strip() for m in os.getenv(
    "GEMINI_LIVE_FALLBACKS", "gemini-3.1-flash-live-preview").split(",")
    if m.strip() and m.strip() != GEMINI_LIVE_MODEL]
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
CLIENT_SECRETS = str(BASE_DIR / os.getenv("GOOGLE_CLIENT_SECRETS", "credentials.json"))
# On a host (Render/Cloud Run) the OAuth client JSON comes from a secret env var instead of a file
if os.getenv("GOOGLE_CREDENTIALS_JSON") and not Path(CLIENT_SECRETS).exists():
    Path(CLIENT_SECRETS).write_text(os.getenv("GOOGLE_CREDENTIALS_JSON"), encoding="utf-8")
# Deployed: set PUBLIC_URL (e.g. https://studypilot.onrender.com) and both of these follow it
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
if PUBLIC_URL:
    os.environ.setdefault("OAUTH_REDIRECT_URI", f"{PUBLIC_URL}/auth/callback")
    os.environ.setdefault("FRONTEND_URL", PUBLIC_URL)
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Karachi")
STUDY_WINDOW_START = os.getenv("STUDY_WINDOW_START", "09:00")
STUDY_WINDOW_END = os.getenv("STUDY_WINDOW_END", "23:00")
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
SYNC_INTERVAL_SECONDS = 10 if DEMO_MODE else int(os.getenv("SYNC_INTERVAL_SECONDS", "30"))
# Where the database + lecture cache live. On a server, point DATA_DIR at a persistent disk
# (e.g. /data) so the Google sign-in and everything StudyPilot learned survive restarts/redeploys.
DATA_DIR = Path(os.getenv("DATA_DIR") or BASE_DIR)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DATA_DIR / "studypilot.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Phone alerts via a private Discord channel webhook (works where Telegram/WhatsApp APIs don't)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
# WhatsApp alerts via Meta's official WhatsApp Cloud API (needs a verified business)
WA_TOKEN = os.getenv("WA_TOKEN", "")
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID", "")
WA_TO = os.getenv("WA_TO", "")  # the student's WhatsApp number, e.g. +923001234567
# Phone push notifications via the free ntfy app (pick a long random topic name)
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
# WhatsApp alerts via CallMeBot (free): the student's number + the key CallMeBot sends them
CALLMEBOT_PHONE = os.getenv("CALLMEBOT_PHONE", "")
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY", "")
# Optional: WhatsApp via Twilio (sandbox number by default)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM") or "whatsapp:+14155238886"
WHATSAPP_TO = os.getenv("WHATSAPP_TO", "")  # the student's number, e.g. +923001234567
# Gemini decides what to do on each change (False = fixed rule-based pipeline)
AGENT_BRAIN = os.getenv("AGENT_BRAIN", "true").lower() == "true"

# ADK / google-genai read the key from this env var
if GEMINI_API_KEY:
    os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",        # create the StudyPilot folder + notes only
    "https://www.googleapis.com/auth/gmail.readonly",    # read class emails, never send
    "https://www.googleapis.com/auth/gmail.compose",     # internship applications as DRAFTS; the student presses Send
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]
