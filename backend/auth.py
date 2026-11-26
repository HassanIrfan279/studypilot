"""Google OAuth: login redirect, callback, token storage + auto refresh."""
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

import db
from config import CLIENT_SECRETS, OAUTH_REDIRECT_URI, SCOPES

_pending = {}  # state -> PKCE code_verifier, kept between /login and /callback


def _flow(state=None):
    return Flow.from_client_secrets_file(CLIENT_SECRETS, scopes=SCOPES,
                                         redirect_uri=OAUTH_REDIRECT_URI, state=state)


def login_url() -> str:
    flow = _flow()
    url, state = flow.authorization_url(access_type="offline", prompt="consent",
                                        include_granted_scopes="true")
    _pending[state] = flow.code_verifier
    return url


def handle_callback(full_url: str, state: str):
    flow = _flow(state)
    flow.code_verifier = _pending.pop(state, None)
    token = flow.fetch_token(authorization_response=full_url)
    granted = token.get("scope", [])
    if isinstance(granted, str):
        granted = granted.split()
    # Google reports some scopes under an older alias name; treat them as the same permission
    aliases = {"classroom.coursework.me.readonly": "classroom.student-submissions.me.readonly"}
    short = {g.split("/")[-1] for g in granted}
    missing = [s for s in SCOPES if s.startswith("https://www.googleapis.com/auth/")
               and "userinfo" not in s
               and s.split("/")[-1] not in short
               and aliases.get(s.split("/")[-1]) not in short]
    _save(flow.credentials)
    db.kv_set("missing_scopes", [m.split("/")[-1] for m in missing])
    return missing


def _save(creds: Credentials):
    db.kv_set("token", json.loads(creds.to_json()))


def get_credentials() -> Credentials | None:
    info = db.kv_get("token")
    if not info:
        return None
    # Use the scopes the student actually granted (refresh fails if we ask for more)
    creds = Credentials.from_authorized_user_info(info, info.get("scopes") or SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        _save(creds)
    return creds


def logout():
    db.execute("DELETE FROM kv WHERE key='token'")
