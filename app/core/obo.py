"""On-behalf-of (user) token extraction for Databricks Apps."""

from __future__ import annotations

from fastapi import HTTPException, Request, status


def get_obo_token(request: Request) -> str:
    """Return the caller's Databricks access token for OBO calls.

    Databricks Apps forwards the signed-in user's token in
    ``x-forwarded-access-token`` when user authorization is enabled. For local
    development, an ``Authorization: Bearer <token>`` header is accepted instead.

    Args:
        request: Incoming HTTP request.

    Returns:
        The user's access token.

    Raises:
        HTTPException: 401 if neither header carries a token.
    """
    forwarded = (request.headers.get("x-forwarded-access-token") or "").strip()
    if forwarded:
        return forwarded
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Missing user access token for OBO SQL. Databricks Apps must forward "
            "x-forwarded-access-token (enable user authorization with the sql scope). "
            "Locally pass Authorization: Bearer <user-oauth-token>."
        ),
    )
