"""Official FPVR request HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.candidates import CandidateTokenError
from app.core.http_logging import current_request_id, gateway_error, log_failure
from app.core.obo import bearer_scheme, get_obo_token
from app.core.sql import WarehouseNotConfiguredError
from app.models import ErrorResponse
from app.models.fpvr import (
    AmbiguousSubjectResponse,
    FPVRReportResponse,
    FPVRRequestAccepted,
    FPVRRequestCreate,
    ReportCode,
    RequestStatusValue,
)
from app.models.fpvr1 import (
    FPVR1Report,
    FPVR1ReportData,
    FPVR1RequestAccepted,
    FPVR1RequestCreate,
)
from app.services.fpvr import (
    AmbiguousSubjectError,
    FPVRRequestService,
    OfficialRequestNotFoundError,
    SubjectNotFoundError,
    get_fpvr_request_service,
)
from app.services.reports import ReportQueryError
from app.services.request_log import RequestLogError, get_request_log_service
from app.services.subject_identity import SubjectIdentityQueryError

router = APIRouter(
    prefix="/v1/requests",
    tags=["fpvr-requests"],
    dependencies=[Depends(bearer_scheme)],
)

_RETRY_AFTER_SECONDS = "5"

_ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": AmbiguousSubjectResponse},
    422: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _caller(request: Request) -> str | None:
    """Best available caller identifier for the request log.

    Args:
        request: Incoming HTTP request.

    Returns:
        Email, preferred username, user id, or None.
    """
    email = (request.headers.get("x-forwarded-email") or "").strip()
    preferred = (request.headers.get("x-forwarded-preferred-username") or "").strip()
    user = (request.headers.get("x-forwarded-user") or "").strip()
    return email or preferred or user or None


def _service() -> FPVRRequestService:
    """Return the FPVR request service.

    Returns:
        Shared service instance.
    """
    return get_fpvr_request_service()


def _to_fpvr1(accepted: FPVRRequestAccepted) -> FPVR1RequestAccepted:
    """Map the generic request envelope onto the typed FPVR-1 DTO.

    Args:
        accepted: Service result for any report code.

    Returns:
        FPVR-1 envelope with typed identity, status, and check sections.
    """
    report = None
    if accepted.report is not None:
        report = _to_fpvr1_report(accepted.report)
    return FPVR1RequestAccepted(
        request_id=accepted.request_id,
        status=accepted.status,
        requested_at=accepted.requested_at,
        requested_by=accepted.requested_by,
        resolution_method=accepted.resolution_method,
        report=report,
    )


def _to_fpvr1_report(report: FPVRReportResponse) -> FPVR1Report:
    """Map generic report JSON onto the FPVR-1 data contract.

    Args:
        report: Assembler-backed report payload.

    Returns:
        Typed Application Bundle report.
    """
    data = report.data or {}
    return FPVR1Report(
        code=ReportCode.FPVR_1,
        title=report.title,
        subject=report.subject,
        data=FPVR1ReportData(
            identity=data.get("identity") or [],
            status=data.get("status") or [],
            check=data.get("check") or [],
        ),
    )


@router.post(
    "",
    response_model=FPVRRequestAccepted,
    status_code=201,
    summary="Open an official FPVR request",
    responses=_ERROR_RESPONSES,
)
def create_request(request: Request, body: FPVRRequestCreate, response: Response):
    """Resolve a subject and create an official request if the match is unique.

    SSN is optional. First name, last name, and date of birth that match exactly
    one person is enough. Multiple matches return 409 without SSN.

    Sets ``Location`` to the new request. Sets ``Retry-After`` when status is
    pending.
    \f
    Args:
        request: Incoming request carrying the caller token.
        body: Report code and identity filters or candidate_id.
        response: FastAPI response used to set Location / Retry-After.

    Returns:
        request_id and initial status. ``report`` is the payload when ready,
        otherwise ``null``.

    Raises:
        HTTPException: 401/404/409/422/502/503 depending on resolution and SQL.
    """
    token = get_obo_token(request)
    try:
        accepted = _service().create(body, user_token=token, requested_by=_caller(request))
        response.headers["Location"] = f"/api/v1/requests/{accepted.request_id}"
        if accepted.status == RequestStatusValue.pending:
            response.headers["Retry-After"] = _RETRY_AFTER_SECONDS
        return accepted
    except CandidateTokenError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from e
    except SubjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except AmbiguousSubjectError as e:
        content = e.response.model_dump(mode="json")
        content["request_id"] = current_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=content,
            headers={"X-Request-Id": current_request_id(request)},
        )
    except WarehouseNotConfiguredError as e:
        log_failure(request, e, step="warehouse", report_code=body.report_code)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except SubjectIdentityQueryError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="identity_sql",
            report_code=body.report_code,
        ) from e
    except ReportQueryError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="report_sql",
            report_code=body.report_code,
        ) from e
    except RequestLogError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="request_log",
            report_code=body.report_code,
        ) from e


@router.post(
    "/fpvr-1",
    response_model=FPVR1RequestAccepted,
    status_code=201,
    summary="Open an official FPVR-1 Application Bundle request",
    responses=_ERROR_RESPONSES,
)
def create_fpvr1_request(request: Request, body: FPVR1RequestCreate, response: Response):
    """Create an FPVR-1 request. Report code is implied by the path.

    Uses the same service as POST /v1/requests. Returns a typed Application
    Bundle payload when ready.
    \f
    Args:
        request: Incoming request carrying the caller token.
        body: Identity filters or candidate_id.
        response: FastAPI response used to set Location / Retry-After.

    Returns:
        FPVR-1 envelope. ``report`` is set when ready.

    Raises:
        HTTPException: 401/404/409/422/502/503 depending on resolution and SQL.
    """
    token = get_obo_token(request)
    create_body = FPVRRequestCreate(
        report_code=ReportCode.FPVR_1,
        ssn=body.ssn,
        first_name=body.first_name,
        last_name=body.last_name,
        date_of_birth=body.date_of_birth,
        candidate_id=body.candidate_id,
    )
    try:
        accepted = _service().create(
            create_body, user_token=token, requested_by=_caller(request)
        )
        response.headers["Location"] = f"/api/v1/requests/fpvr-1/{accepted.request_id}"
        if accepted.status == RequestStatusValue.pending:
            response.headers["Retry-After"] = _RETRY_AFTER_SECONDS
        return _to_fpvr1(accepted)
    except CandidateTokenError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from e
    except SubjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except AmbiguousSubjectError as e:
        content = e.response.model_dump(mode="json")
        content["request_id"] = current_request_id(request)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=content,
            headers={"X-Request-Id": current_request_id(request)},
        )
    except WarehouseNotConfiguredError as e:
        log_failure(request, e, step="warehouse", report_code=ReportCode.FPVR_1.value)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except SubjectIdentityQueryError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="identity_sql",
            report_code=ReportCode.FPVR_1.value,
        ) from e
    except ReportQueryError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="report_sql",
            report_code=ReportCode.FPVR_1.value,
        ) from e
    except RequestLogError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="request_log",
            report_code=ReportCode.FPVR_1.value,
        ) from e


@router.get(
    "/fpvr-1/{request_id}",
    response_model=FPVR1RequestAccepted,
    summary="Get an official FPVR-1 Application Bundle request",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def get_fpvr1_request(
    request: Request, request_id: str, response: Response
) -> FPVR1RequestAccepted:
    """Return the same typed body as POST /v1/requests/fpvr-1.

    Uses the same service as GET /v1/requests/{request_id}. Unknown ids or
    requests logged for another report code return 404.
    \f
    Args:
        request: Incoming request carrying the caller token.
        request_id: Handle from POST /v1/requests/fpvr-1.
        response: FastAPI response used to set Retry-After.

    Returns:
        FPVR-1 envelope. ``report`` is set when ready.

    Raises:
        HTTPException: 401/404/502/503.
    """
    token = get_obo_token(request)
    try:
        row = get_request_log_service().get(request_id, user_token=token)
        if row is None or row.get("report_code") != ReportCode.FPVR_1.value:
            raise OfficialRequestNotFoundError(request_id)
        accepted = _service().get(request_id, user_token=token)
        if accepted.status == RequestStatusValue.pending:
            response.headers["Retry-After"] = _RETRY_AFTER_SECONDS
        return _to_fpvr1(accepted)
    except OfficialRequestNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found") from e
    except WarehouseNotConfiguredError as e:
        log_failure(request, e, step="warehouse", fpvr_request_id=request_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except SubjectIdentityQueryError as e:
        raise gateway_error(
            request, e, detail="Status lookup failed", step="identity_sql",
            fpvr_request_id=request_id,
        ) from e
    except ReportQueryError as e:
        raise gateway_error(
            request, e, detail="Status lookup failed", step="report_sql",
            fpvr_request_id=request_id,
        ) from e
    except RequestLogError as e:
        raise gateway_error(
            request, e, detail="Status lookup failed", step="request_log",
            fpvr_request_id=request_id,
        ) from e


@router.get(
    "/{request_id}",
    response_model=FPVRRequestAccepted,
    summary="Get an official FPVR request",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def get_request(request: Request, request_id: str, response: Response) -> FPVRRequestAccepted:
    """Return the same body as POST. Pending requests re-check Unity Catalog.

    ``report`` is the payload when ready, otherwise ``null``. Sets
    ``Retry-After`` when status is still pending.
    \f
    Args:
        request: Incoming request carrying the caller token.
        request_id: Handle from POST /v1/requests.
        response: FastAPI response used to set Retry-After.

    Returns:
        Request metadata and nested report when ready.

    Raises:
        HTTPException: 401/404/502/503.
    """
    token = get_obo_token(request)
    try:
        accepted = _service().get(request_id, user_token=token)
        if accepted.status == RequestStatusValue.pending:
            response.headers["Retry-After"] = _RETRY_AFTER_SECONDS
        return accepted
    except OfficialRequestNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found") from e
    except WarehouseNotConfiguredError as e:
        log_failure(request, e, step="warehouse", fpvr_request_id=request_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except SubjectIdentityQueryError as e:
        raise gateway_error(
            request, e, detail="Report query failed", step="identity_sql",
            fpvr_request_id=request_id,
        ) from e
    except ReportQueryError as e:
        raise gateway_error(
            request, e, detail="Report query failed", step="report_sql",
            fpvr_request_id=request_id,
        ) from e
    except RequestLogError as e:
        raise gateway_error(
            request, e, detail="Report query failed", step="request_log",
            fpvr_request_id=request_id,
        ) from e
