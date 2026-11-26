"""Builds Google API clients and provides a retry helper with exponential backoff."""
import time

from googleapiclient.discovery import build

from auth import get_credentials


class NotLoggedIn(Exception):
    pass


def _service(name, version):
    creds = get_credentials()
    if not creds:
        raise NotLoggedIn("Please sign in with Google first.")
    # A fresh client per call keeps things thread-safe (httplib2 is not).
    return build(name, version, credentials=creds, cache_discovery=False)


def classroom():
    return _service("classroom", "v1")


def drive():
    return _service("drive", "v3")


def calendar():
    return _service("calendar", "v3")


def oauth2():
    return _service("oauth2", "v2")


def with_retry(fn, attempts=3, base_delay=1.0):
    """Run fn(); on failure wait 1s, 2s, 4s... then re-raise the last error."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except NotLoggedIn:
            raise
        except Exception as e:  # network errors, 429, 5xx
            last = e
            status = getattr(getattr(e, "resp", None), "status", None)
            if status in (400, 401, 403, 404):
                raise  # retrying won't help
            time.sleep(base_delay * (2 ** i))
    raise last
