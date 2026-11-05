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


def get_app_sp_token(
    *, fallback_token: str | None = None, workspace_url: str | None = None
) -> str:
    """Return an OAuth access token for the Databricks App service principal.

    Resolution order:

    1. ``DATABRICKS_TOKEN`` when set. It is used as-is, without an OIDC call.
       CI sets it from the token it already minted for the Postman run.
    2. A cached client-credentials token, if still valid.
    3. OAuth client credentials (``DATABRICKS_CLIENT_ID`` /
       ``DATABRICKS_CLIENT_SECRET``) with ``scope=sql`` and ``scopes=jobs``.
    4. ``fallback_token`` (the caller OBO token) when no client credentials
       are configured.

    Args:
        fallback_token: Caller token used only when neither ``DATABRICKS_TOKEN``
            nor App SP client credentials are configured.
        workspace_url: Workspace host used for the OIDC token request. When
            omitted, ``workspace_host()`` (settings) is used. Pass this when
            calling from ``get_settings()`` to avoid recursion.

    Returns:
        A Bearer access token for App SP SQL, Jobs, or Unity Catalog calls.

    Raises:
        AppPrincipalError: If no usable token can be obtained.
    """
    global _cached_token, _cached_until

    injected_token = os.getenv("DATABRICKS_TOKEN", "").strip()
    if injected_token:
        return injected_token

    now = time.time()
    with _lock:
        if _cached_token and now < _cached_until:
            return _cached_token

    client_id = os.getenv("DATABRICKS_CLIENT_ID", "").strip()
    client_secret = os.getenv("DATABRICKS_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        if fallback_token and fallback_token.strip():
            return fallback_token.strip()
        raise AppPrincipalError(
            "DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET are required "
            "to discover Unity Catalog schemas and start pending-report jobs. "
            "Locally set DATABRICKS_TOKEN instead."
        )

    try:
        host = (workspace_url or workspace_host()).strip().rstrip("/")
    except Exception as exc:
        raise AppPrincipalError(str(exc)) from exc
    if not host:
        raise AppPrincipalError("Databricks workspace host is not set")

    body = urlencode(
        {"grant_type": "client_credentials", "scope": "sql", "scopes": "jobs"}
    ).encode()
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
