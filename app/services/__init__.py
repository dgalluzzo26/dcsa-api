"""Domain services (business logic + persistence adapters).

Services hold business rules and data access. They raise domain exceptions and
never raise ``HTTPException``; routes translate those exceptions into HTTP errors.
"""

from __future__ import annotations

from app.services.fpvr import (
    AmbiguousSubjectError,
    FPVRRequestService,
    OfficialRequestNotFoundError,
    SubjectNotFoundError,
    get_fpvr_request_service,
)
from app.services.reports import ReportAssembler, ReportQueryError, get_report_assembler
from app.services.request_log import RequestLogError, RequestLogService, get_request_log_service
from app.services.subject_identity import (
    SubjectIdentityQueryError,
    SubjectIdentityService,
    get_subject_identity_service,
)

__all__ = [
    "AmbiguousSubjectError",
    "FPVRRequestService",
    "OfficialRequestNotFoundError",
    "ReportAssembler",
    "ReportQueryError",
    "RequestLogError",
    "RequestLogService",
    "SubjectIdentityQueryError",
    "SubjectIdentityService",
    "SubjectNotFoundError",
    "get_fpvr_request_service",
    "get_report_assembler",
    "get_request_log_service",
    "get_subject_identity_service",
]
