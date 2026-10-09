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
    FPVRRequestAccepted,
    FPVRRequestCreate,
    RequestStatusValue,
)
from app.services.fpvr import (
    AmbiguousSubjectError,
    FPVRRequestService,
    OfficialRequestNotFoundError,
    SubjectNotFoundError,
    get_fpvr_request_service,
)
from app.services.reports import ReportQueryError
from app.services.request_log import RequestLogError
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
        log_failure(request, e, step="warehouse", report_code=body.report_code.value)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except SubjectIdentityQueryError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="identity_sql",
            report_code=body.report_code.value,
        ) from e
    except ReportQueryError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="report_sql",
            report_code=body.report_code.value,
        ) from e
    except RequestLogError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="request_log",
            report_code=body.report_code.value,
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
            request, e, detail="Request lookup failed", step="identity_sql",
            fpvr_request_id=request_id,
        ) from e
    except ReportQueryError as e:
        raise gateway_error(
            request, e, detail="Request lookup failed", step="report_sql",
            fpvr_request_id=request_id,
        ) from e
    except RequestLogError as e:
        raise gateway_error(
            request, e, detail="Request lookup failed", step="request_log",
            fpvr_request_id=request_id,
        ) from e
