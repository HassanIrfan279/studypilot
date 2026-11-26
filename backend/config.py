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
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL") or "gemini-2.5-flash-native-audio-preview-12-2025"
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
CLIENT_SECRETS = str(BASE_DIR / os.getenv("GOOGLE_CLIENT_SECRETS", "credentials.json"))
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Karachi")
STUDY_WINDOW_START = os.getenv("STUDY_WINDOW_START", "09:00")
STUDY_WINDOW_END = os.getenv("STUDY_WINDOW_END", "23:00")
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
SYNC_INTERVAL_SECONDS = 10 if DEMO_MODE else int(os.getenv("SYNC_INTERVAL_SECONDS", "30"))
DB_PATH = str(BASE_DIR / "studypilot.db")

# ADK / google-genai read the key from this env var
if GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY
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
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
]
