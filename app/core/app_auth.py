"""App service principal OAuth for request-log writes."""

from __future__ import annotations

import json
import os
import time
from base64 import b64encode
from threading import Lock
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.sql import workspace_host


class AppPrincipalError(RuntimeError):
    """Raised when the app service principal cannot obtain an access token."""


_lock = Lock()
_cached_token: str | None = None
_cached_until: float = 0.0


def get_app_sp_token() -> str:
    """Return an OAuth access token for the Databricks App service principal.

    Databricks Apps inject ``DATABRICKS_CLIENT_ID`` and
    ``DATABRICKS_CLIENT_SECRET``. The token is cached until shortly before
    expiry.

    Returns:
        A Bearer access token for App SP SQL (request log only).

    Raises:
        AppPrincipalError: If client credentials are missing or the token
            endpoint rejects the request.
    """
    global _cached_token, _cached_until
    now = time.time()
    with _lock:
        if _cached_token and now < _cached_until:
            return _cached_token

    client_id = os.getenv("DATABRICKS_CLIENT_ID", "").strip()
    client_secret = os.getenv("DATABRICKS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        local_token = os.getenv("DATABRICKS_TOKEN", "").strip()
        if local_token:
            return local_token
        raise AppPrincipalError(
            "DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET are required "
            "for App SP request logging. Locally set DATABRICKS_TOKEN instead."
        )

    try:
        host = workspace_host()
    except Exception as exc:
        raise AppPrincipalError(str(exc)) from exc

    body = urlencode({"grant_type": "client_credentials", "scope": "all-apis"}).encode()
    basic = b64encode(f"{client_id}:{client_secret}".encode()).decode()
    request = Request(
        f"{host}/oidc/v1/token",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except Exception as exc:
        raise AppPrincipalError(f"App SP token request failed: {exc}") from exc

    token = payload.get("access_token")
    if not token:
        raise AppPrincipalError("App SP token response did not include access_token")
    expires_in = int(payload.get("expires_in") or 3600)
    with _lock:
        _cached_token = token
        _cached_until = time.time() + max(expires_in - 60, 30)
    return token
