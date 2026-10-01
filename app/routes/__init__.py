"""HTTP routes — thin controllers over services.

Route handlers parse HTTP input, call a service, and map domain exceptions to
HTTP status codes. Business logic belongs in ``app.services``. Domain routers
live in their own modules and are included here.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__
from app.core.config import get_settings
from app.models import HealthResponse, MeResponse
from app.routes.fpvr import router as fpvr_router
from app.routes.subject_identity import router as subject_identity_router

router = APIRouter()
router.include_router(subject_identity_router)
router.include_router(fpvr_router)


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Health check",
)
def health() -> HealthResponse:
    """Report that the service is running.
    \f
    Returns:
        Service status, name, environment and version.
    """
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.environment,
        version=__version__,
    )


@router.get(
    "/me",
    response_model=MeResponse,
    tags=["system"],
    summary="Signed-in identity (Databricks Apps headers)",
)
def me(request: Request) -> MeResponse:
    """Return the signed-in caller as seen through Databricks Apps headers.
    \f
    Args:
        request: Incoming HTTP request.

    Returns:
        The caller's identity fields and where they came from.
    """
    email = (request.headers.get("x-forwarded-email") or "").strip() or None
    user = (request.headers.get("x-forwarded-user") or "").strip() or None
    preferred = (request.headers.get("x-forwarded-preferred-username") or "").strip() or None
    identity = email or preferred or user
    source = "header" if identity else "none"
    return MeResponse(identity=identity, email=email, user=user, source=source)
