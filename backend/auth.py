"""Google OAuth: login redirect, callback, token storage + auto refresh."""
import json

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

import db
from config import CLIENT_SECRETS, OAUTH_REDIRECT_URI, SCOPES

_pending = {}  # state -> PKCE code_verifier, kept between /login and /callback


class NotOwner(Exception):
    """Someone other than the owner tried to sign in. StudyPilot is one student's personal agent."""


def _email(creds) -> str:
    from googleapiclient.discovery import build
    svc = build("oauth2", "v2", credentials=creds, cache_discovery=False)
    return (svc.userinfo().get().execute().get("email") or "").lower()


def owner_email():
    """The account this StudyPilot belongs to: OWNER_EMAIL env, else the first account that signed in."""
    import os
    return (os.getenv("OWNER_EMAIL") or db.kv_get("owner_email") or "").lower() or None


def _revoke(creds):
    import requests
    try:
        requests.post("https://oauth2.googleapis.com/revoke", params={"token": creds.token},
                      headers={"content-type": "application/x-www-form-urlencoded"}, timeout=10)
    except Exception:
        pass


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
    # Owner lock: only the student this StudyPilot belongs to may sign in. Checked BEFORE saving,
    # so a stranger signing in can never replace (or sign out) the owner's account.
    email = _email(flow.credentials)
    owner = owner_email()
    if not owner and db.kv_get("token"):
        current = get_credentials()
        owner = _email(current) if current else None
    if owner and email != owner:
        _revoke(flow.credentials)
        raise NotOwner(email)
    if missing:
        return missing  # nothing saved: the owner's existing sign-in stays as it was
    _save(flow.credentials)
    db.kv_set("owner_email", email)
    import time
    db.kv_set("token_issued", time.time())
    db.execute("DELETE FROM kv WHERE key='signin_warned'")
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
        try:
            creds.refresh(Request())
        except RefreshError:
            # Testing-mode Google apps expire refresh tokens after 7 days -> show Sign in again
            logout()
            from activity_log import log
            log("Coordinator", "Google sign-in expired. Please sign in again.", "error")
            return None
        _save(creds)
    return creds


def logout():
    db.execute("DELETE FROM kv WHERE key='token'")
