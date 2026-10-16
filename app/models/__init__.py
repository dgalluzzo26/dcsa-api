"""Pydantic request/response models.

Models define the API contract only. They hold no persistence or HTTP logic so
they can be shared by routes and services without circular dependencies.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.models.fpvr import (
    AmbiguousSubjectResponse,
    FPVRReportResponse,
    FPVRRequestAccepted,
    FPVRRequestCreate,
    FPVRRequestStatus,
    RequestStatusValue,
    SubjectCandidate,
)
from app.models.report_contract import ApiCatalog
from app.models.subject_identity import (
    SubjectIdentity,
    SubjectIdentityListResponse,
    SubjectIdentitySearch,
)


class HealthResponse(BaseModel):
    """Response body for the health check endpoint.

    Attributes:
        status: Health status, ``"ok"`` when the service is running.
        app: Application name.
        environment: Deployment environment (for example ``dev``).
        version: Application version.
    """

    status: str = "ok"
    app: str
    environment: str
    version: str


class MeResponse(BaseModel):
    """Caller identity derived from Databricks Apps forwarded headers.

    Attributes:
        identity: Best available identifier (email, preferred username, or user).
        email: Value of ``x-forwarded-email``.
        user: Value of ``x-forwarded-user``.
        source: ``"header"`` when an identity was found, otherwise ``"none"``.
    """

    identity: str | None = None
    email: str | None = None
    user: str | None = None
    source: str = "none"


class ErrorResponse(BaseModel):
    """Standard error body returned with non-2xx responses.

    Attributes:
        detail: Human-readable error message.
        request_id: Correlation id also sent as ``X-Request-Id``.
    """

    detail: str
    request_id: str | None = None


__all__ = [
    "AmbiguousSubjectResponse",
    "ApiCatalog",
    "ErrorResponse",
    "FPVRReportResponse",
    "FPVRRequestAccepted",
    "FPVRRequestCreate",
    "FPVRRequestStatus",
    "HealthResponse",
    "MeResponse",
    "RequestStatusValue",
    "SubjectCandidate",
    "SubjectIdentity",
    "SubjectIdentityListResponse",
    "SubjectIdentitySearch",
]
