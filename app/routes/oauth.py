"""OAuth2 client_credentials token proxy to the Databricks workspace."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.sql import WarehouseNotConfiguredError, workspace_host
from app.models import ErrorResponse
from app.models.fpvr import TokenResponse

router = APIRouter(tags=["oauth"])


class TokenRequest(BaseModel):
    """Client credentials submitted to mint a Databricks access token.

    Attributes:
        grant_type: Must be ``client_credentials``.
        client_id: Databricks service principal application id.
        client_secret: Service principal secret.
        scope: OAuth scope requested from Databricks.
    """

    grant_type: str = "client_credentials"
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    scope: str = "all-apis"


@router.post(
    "/oauth/token",
    response_model=TokenResponse,
    summary="Exchange client_id and client_secret for a Databricks token",
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
def create_token(body: TokenRequest) -> TokenResponse:
    """Proxy OAuth2 client_credentials to the workspace OIDC token endpoint.

    Use the returned Bearer token on later FPVR calls.
    \f
    Args:
        body: Client id, secret, and grant type.

    Returns:
        Access token and expiry.

    Raises:
        HTTPException: 400 if grant_type is unsupported, 401 if Databricks
            rejects the credentials.
    """
    if body.grant_type != "client_credentials":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="grant_type must be client_credentials",
        )
    try:
        host = workspace_host()
    except WarehouseNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e

    encoded = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": body.client_id,
            "client_secret": body.client_secret,
            "scope": body.scope,
        }
    ).encode()
    req = UrlRequest(
        f"{host}/oidc/v1/token",
        data=encoded,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(req, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client_id or client_secret",
        ) from exc
    except URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Token endpoint is unreachable",
        ) from exc

    token = payload.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Token response missing access_token",
        )
    expires = payload.get("expires_in")
    return TokenResponse(
        access_token=token,
        token_type=str(payload.get("token_type") or "Bearer"),
        expires_in=int(expires) if expires is not None else None,
    )
