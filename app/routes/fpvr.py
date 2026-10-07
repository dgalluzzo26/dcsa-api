"""Official FPVR request HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Security, status
from fastapi.responses import JSONResponse

from app.core.candidates import CandidateTokenError
from app.core.obo import bearer_scheme, get_obo_token
from app.core.sql import WarehouseNotConfiguredError
from app.models import ErrorResponse
from app.models.fpvr import (
    AmbiguousSubjectResponse,
    FPVRReportResponse,
    FPVRRequestAccepted,
    FPVRRequestCreate,
    FPVRRequestStatus,
)
from app.services.fpvr import (
    AmbiguousSubjectError,
    FPVRRequestService,
    OfficialRequestNotFoundError,
    RequestNotReadyError,
    SubjectNotFoundError,
    get_fpvr_request_service,
)
from app.services.reports import ReportQueryError
from app.services.request_log import RequestLogError
from app.services.subject_identity import SubjectIdentityQueryError

router = APIRouter(
    prefix="/v1/requests",
    tags=["fpvr-requests"],
    dependencies=[Security(bearer_scheme)],
)

_ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": AmbiguousSubjectResponse},
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
    status_code=200,
    summary="Open an official FPVR request",
    responses=_ERROR_RESPONSES,
)
def create_request(request: Request, body: FPVRRequestCreate):
    """Resolve a subject and create an official request if the match is unique.

    SSN is optional. First name, last name, and date of birth that match exactly
    one person is enough. Multiple matches return 409 without SSN.
    \f
    Args:
        request: Incoming request carrying the caller token.
        body: Report code and identity filters or candidate_id.

    Returns:
        request_id and initial status.

    Raises:
        HTTPException: 400/401/404/409/502/503 depending on resolution and SQL.
    """
    token = get_obo_token(request)
    try:
        return _service().create(body, user_token=token, requested_by=_caller(request))
    except CandidateTokenError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except SubjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except AmbiguousSubjectError as e:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content=e.response.model_dump(mode="json")
        )
    except WarehouseNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except (SubjectIdentityQueryError, ReportQueryError, RequestLogError) as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.get(
    "/{request_id}",
    response_model=FPVRRequestStatus,
    summary="Get FPVR request status",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def get_request_status(request: Request, request_id: str) -> FPVRRequestStatus:
    """Poll whether a request is pending, ready, or failed.

    Pending requests re-check Unity Catalog on each poll and may become ready.
    \f
    Args:
        request: Incoming request carrying the caller token.
        request_id: Handle from POST /v1/requests.

    Returns:
        Status without SSN.

    Raises:
        HTTPException: 401/404/502/503.
    """
    token = get_obo_token(request)
    try:
        return _service().status(request_id, user_token=token)
    except OfficialRequestNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found") from e
    except WarehouseNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except (SubjectIdentityQueryError, ReportQueryError, RequestLogError) as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.get(
    "/{request_id}/response",
    response_model=FPVRReportResponse,
    summary="Get FPVR report payload",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
def get_request_response(request: Request, request_id: str) -> FPVRReportResponse:
    """Return report data for a ready request. Queries Unity Catalog as the caller (OBO).
    \f
    Args:
        request: Incoming request carrying the caller token.
        request_id: Handle from POST /v1/requests.

    Returns:
        Report JSON without SSN.

    Raises:
        HTTPException: 409 if not ready, plus 401/404/502/503.
    """
    token = get_obo_token(request)
    try:
        return _service().response(request_id, user_token=token)
    except OfficialRequestNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found") from e
    except RequestNotReadyError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Request is not ready",
        ) from e
    except WarehouseNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except (SubjectIdentityQueryError, ReportQueryError, RequestLogError) as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
