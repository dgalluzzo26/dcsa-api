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
    OfficialReport,
    OfficialRequestAccepted,
    OfficialRequestCreate,
    SubjectCandidate,
)
from app.models.reports.fpvr1 import FPVR1RequestAccepted
from app.models.reports.fpvr2 import FPVR2RequestAccepted
from app.models.reports.fpvr3 import FPVR3RequestAccepted
from app.models.reports.fpvr4 import FPVR4RequestAccepted
from app.models.reports.fpvr5 import FPVR5RequestAccepted
from app.models.reports.fpvr6 import FPVR6RequestAccepted
from app.models.reports.fpvr7 import FPVR7RequestAccepted
from app.models.reports.awards import AWARDSRequestAccepted
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
    "AWARDSRequestAccepted",
    "AmbiguousSubjectResponse",
    "ApiCatalog",
    "ErrorResponse",
    "FPVR1RequestAccepted",
    "FPVR2RequestAccepted",
    "FPVR3RequestAccepted",
    "FPVR4RequestAccepted",
    "FPVR5RequestAccepted",
    "FPVR6RequestAccepted",
    "FPVR7RequestAccepted",
    "FPVRReportResponse",
    "FPVRRequestAccepted",
    "FPVRRequestCreate",
    "HealthResponse",
    "MeResponse",
    "OfficialReport",
    "OfficialRequestAccepted",
    "OfficialRequestCreate",
    "RequestStatusValue",
    "SubjectCandidate",
    "SubjectIdentity",
    "SubjectIdentityListResponse",
    "SubjectIdentitySearch",
]
