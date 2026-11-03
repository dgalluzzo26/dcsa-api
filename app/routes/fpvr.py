"""Official FPVR request HTTP routes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.candidates import CandidateTokenError
from app.core.http_logging import current_request_id, gateway_error, log_failure
from app.core.obo import bearer_scheme, get_obo_token
from app.core.sql import WarehouseNotConfiguredError
from app.models import ErrorResponse
from app.models.fpvr import (
    AmbiguousSubjectResponse,
    FPVRRequestAccepted,
    FPVRRequestCreate,
    FPVRRequestListQuery,
    FPVRSubjectCreate,
    ReportCode,
    RequestSource,
    RequestStatusValue,
)
from app.models.fpvr1 import (
    FPVR1Report,
    FPVR1ReportData,
    FPVR1RequestAccepted,
    FPVR1RequestCreate,
    FPVR1RequestListResponse,
)
from app.models.fpvr_reports import (
    FPVR2Report,
    FPVR2ReportData,
    FPVR2RequestAccepted,
    FPVR2RequestCreate,
    FPVR2RequestListResponse,
    FPVR3Report,
    FPVR3ReportData,
    FPVR3RequestAccepted,
    FPVR3RequestCreate,
    FPVR3RequestListResponse,
    FPVR4Report,
    FPVR4ReportData,
    FPVR4RequestAccepted,
    FPVR4RequestCreate,
    FPVR4RequestListResponse,
    FPVR5Report,
    FPVR5ReportData,
    FPVR5RequestAccepted,
    FPVR5RequestCreate,
    FPVR5RequestListResponse,
    FPVR6Report,
    FPVR6ReportData,
    FPVR6RequestAccepted,
    FPVR6RequestCreate,
    FPVR6RequestListResponse,
    FPVR7Report,
    FPVR7ReportData,
    FPVR7RequestAccepted,
    FPVR7RequestCreate,
    FPVR7RequestListResponse,
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
    400: {"model": ErrorResponse},
    409: {"model": AmbiguousSubjectResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}

_GET_ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}

_LIST_ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}

TypedMapper = Callable[[FPVRRequestAccepted], object]


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


def _slug(code: ReportCode) -> str:
    """Return the URL slug for a report code.

    Args:
        code: FPVR report code.

    Returns:
        Lowercase path segment such as ``fpvr-1``.
    """
    return code.value.lower()


def _to_typed(
    accepted: FPVRRequestAccepted,
    *,
    accepted_cls: type,
    report_cls: type,
    data_cls: type,
    code: ReportCode,
    sections: tuple[str, ...],
) -> object:
    """Map the generic request envelope onto a typed report DTO.

    Args:
        accepted: Service result for any report code.
        accepted_cls: Path-specific accepted envelope.
        report_cls: Path-specific report model.
        data_cls: Path-specific ``data`` model.
        code: Report implied by the route.
        sections: ``data`` section names in contract order.

    Returns:
        Typed envelope with section lists copied from the assembler payload.
    """
    report = None
    if accepted.report is not None:
        payload = accepted.report.data or {}
        report = report_cls(
            code=code,
            title=accepted.report.title,
            subject=accepted.report.subject,
            data=data_cls(**{name: payload.get(name) or [] for name in sections}),
        )
    return accepted_cls(
        request_id=accepted.request_id,
        status=accepted.status,
        requested_at=accepted.requested_at,
        requested_by=accepted.requested_by,
        resolution_method=accepted.resolution_method,
        source=accepted.source,
        report=report,
    )


def _create_typed(
    request: Request,
    body: FPVRSubjectCreate,
    response: Response,
    code: ReportCode,
    mapper: TypedMapper,
) -> object:
    """Resolve a subject and log an official request for one report code.

    Args:
        request: Incoming request carrying the caller token.
        body: Identity filters or candidate_id.
        response: FastAPI response used to set Location / Retry-After.
        code: Report implied by the route.
        mapper: Converts the generic envelope to the typed DTO.

    Returns:
        Typed request envelope.

    Raises:
        HTTPException: 400/401/404/409/502/503 depending on resolution and SQL.
    """
    token = get_obo_token(request)
    slug = _slug(code)
    create_body = FPVRRequestCreate(
        report_code=code,
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
        response.headers["Location"] = f"/api/v1/requests/{slug}/{accepted.request_id}"
        if accepted.status == RequestStatusValue.pending:
            response.headers["Retry-After"] = _RETRY_AFTER_SECONDS
        return mapper(accepted)
    except CandidateTokenError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
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
        log_failure(request, e, step="warehouse", report_code=code.value)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except SubjectIdentityQueryError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="identity_sql",
            report_code=code.value,
        ) from e
    except ReportQueryError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="report_sql",
            report_code=code.value,
        ) from e
    except RequestLogError as e:
        raise gateway_error(
            request, e, detail="FPVR request failed", step="request_log",
            report_code=code.value,
        ) from e


def _get_typed(
    request: Request, request_id: str, response: Response, code: ReportCode, mapper: TypedMapper
) -> object:
    """Return a typed request envelope for one report code.

    Args:
        request: Incoming request carrying the caller token.
        request_id: Handle from the matching POST.
        response: FastAPI response used to set Retry-After.
        code: Report implied by the route.
        mapper: Converts the generic envelope to the typed DTO.

    Returns:
        Typed request envelope.

    Raises:
        HTTPException: 401/404/502/503.
    """
    token = get_obo_token(request)
    try:
        row = get_request_log_service().get(request_id, user_token=token)
        if row is None or row.get("report_code") != code.value:
            raise OfficialRequestNotFoundError(request_id)
        accepted = _service().get(request_id, user_token=token)
        if accepted.status == RequestStatusValue.pending:
            response.headers["Retry-After"] = _RETRY_AFTER_SECONDS
        return mapper(accepted)
    except OfficialRequestNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found") from e
    except WarehouseNotConfiguredError as e:
        log_failure(request, e, step="warehouse", fpvr_request_id=request_id)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except (SubjectIdentityQueryError, ReportQueryError, RequestLogError) as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


def _list_query(
    status_filter: RequestStatusValue | None = Query(default=None, alias="status"),
    requested_by: str | None = Query(default=None),
    requested_at_after: datetime | None = Query(
        default=None,
        description=(
            "Inclusive lower bound on requested_at (ISO-8601). Alone this is after; "
            "with requested_at_before this is between."
        ),
    ),
    requested_at_before: datetime | None = Query(
        default=None,
        description=(
            "Inclusive upper bound on requested_at (ISO-8601). Alone this is before; "
            "with requested_at_after this is between."
        ),
    ),
    resolution_method: str | None = Query(default=None),
    source: RequestSource | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> FPVRRequestListQuery:
    """Parse list filters from the query string.

    Args:
        status_filter: pending, ready, or failed.
        requested_by: Caller identity stored on the log row.
        requested_at_after: Inclusive lower bound on requested_at.
        requested_at_before: Inclusive upper bound on requested_at.
        resolution_method: unique_match or candidate_id.
        source: internal or external.
        limit: Maximum rows to return.

    Returns:
        Validated list query.

    Raises:
        HTTPException: 400 if the requested_at range is inverted.
    """
    try:
        return FPVRRequestListQuery(
            status=status_filter,
            requested_by=requested_by,
            requested_at_after=requested_at_after,
            requested_at_before=requested_at_before,
            resolution_method=resolution_method,
            source=source,
            limit=limit,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="requested_at_after must be less than or equal to requested_at_before",
        ) from e


def _list_typed(
    request: Request,
    query: FPVRRequestListQuery,
    code: ReportCode,
    mapper: TypedMapper,
    list_cls: type,
) -> object:
    """Return typed request envelopes matching optional filters for one report.

    Args:
        request: Incoming request carrying the caller token.
        query: Optional status, caller, requested_at range, resolution, source.
        code: Report implied by the route.
        mapper: Converts each generic envelope to the typed DTO.
        list_cls: Path-specific list response model.

    Returns:
        Typed list with ``report`` unset.

    Raises:
        HTTPException: 401/400/502/503.
    """
    token = get_obo_token(request)
    try:
        result = _service().list(query, report_code=code, user_token=token)
        return list_cls(items=[mapper(item) for item in result.items], total=result.total)
    except WarehouseNotConfiguredError as e:
        log_failure(request, e, step="warehouse", report_code=code.value)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except RequestLogError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


def _to_fpvr1(accepted: FPVRRequestAccepted) -> FPVR1RequestAccepted:
    """Map the generic envelope onto the FPVR-1 DTO."""
    return _to_typed(
        accepted,
        accepted_cls=FPVR1RequestAccepted,
        report_cls=FPVR1Report,
        data_cls=FPVR1ReportData,
        code=ReportCode.FPVR_1,
        sections=("identity", "status", "check"),
    )


def _to_fpvr2(accepted: FPVRRequestAccepted) -> FPVR2RequestAccepted:
    """Map the generic envelope onto the FPVR-2 DTO."""
    return _to_typed(
        accepted,
        accepted_cls=FPVR2RequestAccepted,
        report_cls=FPVR2Report,
        data_cls=FPVR2ReportData,
        code=ReportCode.FPVR_2,
        sections=("check", "activity"),
    )


def _to_fpvr3(accepted: FPVRRequestAccepted) -> FPVR3RequestAccepted:
    """Map the generic envelope onto the FPVR-3 DTO."""
    return _to_typed(
        accepted,
        accepted_cls=FPVR3RequestAccepted,
        report_cls=FPVR3Report,
        data_cls=FPVR3ReportData,
        code=ReportCode.FPVR_3,
        sections=("status", "check"),
    )


def _to_fpvr4(accepted: FPVRRequestAccepted) -> FPVR4RequestAccepted:
    """Map the generic envelope onto the FPVR-4 DTO."""
    return _to_typed(
        accepted,
        accepted_cls=FPVR4RequestAccepted,
        report_cls=FPVR4Report,
        data_cls=FPVR4ReportData,
        code=ReportCode.FPVR_4,
        sections=("identity", "status"),
    )


def _to_fpvr5(accepted: FPVRRequestAccepted) -> FPVR5RequestAccepted:
    """Map the generic envelope onto the FPVR-5 DTO."""
    return _to_typed(
        accepted,
        accepted_cls=FPVR5RequestAccepted,
        report_cls=FPVR5Report,
        data_cls=FPVR5ReportData,
        code=ReportCode.FPVR_5,
        sections=("signal",),
    )


def _to_fpvr6(accepted: FPVRRequestAccepted) -> FPVR6RequestAccepted:
    """Map the generic envelope onto the FPVR-6 DTO."""
    return _to_typed(
        accepted,
        accepted_cls=FPVR6RequestAccepted,
        report_cls=FPVR6Report,
        data_cls=FPVR6ReportData,
        code=ReportCode.FPVR_6,
        sections=("identity", "status"),
    )


def _to_fpvr7(accepted: FPVRRequestAccepted) -> FPVR7RequestAccepted:
    """Map the generic envelope onto the FPVR-7 DTO."""
    return _to_typed(
        accepted,
        accepted_cls=FPVR7RequestAccepted,
        report_cls=FPVR7Report,
        data_cls=FPVR7ReportData,
        code=ReportCode.FPVR_7,
        sections=("status",),
    )


@router.post(
    "/fpvr-1",
    response_model=FPVR1RequestAccepted,
    status_code=201,
    summary="Open an official FPVR-1 Application Bundle request",
    responses=_ERROR_RESPONSES,
)
def create_fpvr1_request(request: Request, body: FPVR1RequestCreate, response: Response):
    """Create an FPVR-1 request. Report code is implied by the path.

    Returns a typed Application Bundle payload when ready.
    """
    return _create_typed(request, body, response, ReportCode.FPVR_1, _to_fpvr1)


@router.get(
    "/fpvr-1",
    response_model=FPVR1RequestListResponse,
    summary="List official FPVR-1 Application Bundle requests",
    responses=_LIST_ERROR_RESPONSES,
)
def list_fpvr1_requests(
    request: Request, query: FPVRRequestListQuery = Depends(_list_query)
):
    """Return FPVR-1 request log rows matching optional filters.

    Filters AND together. Nested ``report`` is not assembled; GET by id for a ready payload.
    """
    return _list_typed(request, query, ReportCode.FPVR_1, _to_fpvr1, FPVR1RequestListResponse)


@router.get(
    "/fpvr-1/{request_id}",
    response_model=FPVR1RequestAccepted,
    summary="Get an official FPVR-1 Application Bundle request",
    responses=_GET_ERROR_RESPONSES,
)
def get_fpvr1_request(
    request: Request, request_id: str, response: Response
) -> FPVR1RequestAccepted:
    """Return the same typed body as POST /v1/requests/fpvr-1.

    Unknown ids or requests logged for another report code return 404.
    """
    return _get_typed(request, request_id, response, ReportCode.FPVR_1, _to_fpvr1)


@router.post(
    "/fpvr-2",
    response_model=FPVR2RequestAccepted,
    status_code=201,
    summary="Open an official FPVR-2 Investigation Summary request",
    responses=_ERROR_RESPONSES,
)
def create_fpvr2_request(request: Request, body: FPVR2RequestCreate, response: Response):
    """Create an FPVR-2 request. Report code is implied by the path."""
    return _create_typed(request, body, response, ReportCode.FPVR_2, _to_fpvr2)


@router.get(
    "/fpvr-2",
    response_model=FPVR2RequestListResponse,
    summary="List official FPVR-2 Investigation Summary requests",
    responses=_LIST_ERROR_RESPONSES,
)
def list_fpvr2_requests(
    request: Request, query: FPVRRequestListQuery = Depends(_list_query)
):
    """Return FPVR-2 request log rows matching optional filters."""
    return _list_typed(request, query, ReportCode.FPVR_2, _to_fpvr2, FPVR2RequestListResponse)


@router.get(
    "/fpvr-2/{request_id}",
    response_model=FPVR2RequestAccepted,
    summary="Get an official FPVR-2 Investigation Summary request",
    responses=_GET_ERROR_RESPONSES,
)
def get_fpvr2_request(request: Request, request_id: str, response: Response):
    """Return the same typed body as POST /v1/requests/fpvr-2."""
    return _get_typed(request, request_id, response, ReportCode.FPVR_2, _to_fpvr2)


@router.post(
    "/fpvr-3",
    response_model=FPVR3RequestAccepted,
    status_code=201,
    summary="Open an official FPVR-3 Adjudication Summary request",
    responses=_ERROR_RESPONSES,
)
def create_fpvr3_request(request: Request, body: FPVR3RequestCreate, response: Response):
    """Create an FPVR-3 request. Report code is implied by the path."""
    return _create_typed(request, body, response, ReportCode.FPVR_3, _to_fpvr3)


@router.get(
    "/fpvr-3",
    response_model=FPVR3RequestListResponse,
    summary="List official FPVR-3 Adjudication Summary requests",
    responses=_LIST_ERROR_RESPONSES,
)
def list_fpvr3_requests(
    request: Request, query: FPVRRequestListQuery = Depends(_list_query)
):
    """Return FPVR-3 request log rows matching optional filters."""
    return _list_typed(request, query, ReportCode.FPVR_3, _to_fpvr3, FPVR3RequestListResponse)


@router.get(
    "/fpvr-3/{request_id}",
    response_model=FPVR3RequestAccepted,
    summary="Get an official FPVR-3 Adjudication Summary request",
    responses=_GET_ERROR_RESPONSES,
)
def get_fpvr3_request(request: Request, request_id: str, response: Response):
    """Return the same typed body as POST /v1/requests/fpvr-3."""
    return _get_typed(request, request_id, response, ReportCode.FPVR_3, _to_fpvr3)


@router.post(
    "/fpvr-4",
    response_model=FPVR4RequestAccepted,
    status_code=201,
    summary="Open an official FPVR-4 CV Summary request",
    responses=_ERROR_RESPONSES,
)
def create_fpvr4_request(request: Request, body: FPVR4RequestCreate, response: Response):
    """Create an FPVR-4 request. Report code is implied by the path."""
    return _create_typed(request, body, response, ReportCode.FPVR_4, _to_fpvr4)


@router.get(
    "/fpvr-4",
    response_model=FPVR4RequestListResponse,
    summary="List official FPVR-4 CV Summary requests",
    responses=_LIST_ERROR_RESPONSES,
)
def list_fpvr4_requests(
    request: Request, query: FPVRRequestListQuery = Depends(_list_query)
):
    """Return FPVR-4 request log rows matching optional filters."""
    return _list_typed(request, query, ReportCode.FPVR_4, _to_fpvr4, FPVR4RequestListResponse)


@router.get(
    "/fpvr-4/{request_id}",
    response_model=FPVR4RequestAccepted,
    summary="Get an official FPVR-4 CV Summary request",
    responses=_GET_ERROR_RESPONSES,
)
def get_fpvr4_request(request: Request, request_id: str, response: Response):
    """Return the same typed body as POST /v1/requests/fpvr-4."""
    return _get_typed(request, request_id, response, ReportCode.FPVR_4, _to_fpvr4)


@router.post(
    "/fpvr-5",
    response_model=FPVR5RequestAccepted,
    status_code=201,
    summary="Open an official FPVR-5 CV Alerts request",
    responses=_ERROR_RESPONSES,
)
def create_fpvr5_request(request: Request, body: FPVR5RequestCreate, response: Response):
    """Create an FPVR-5 request. Report code is implied by the path."""
    return _create_typed(request, body, response, ReportCode.FPVR_5, _to_fpvr5)


@router.get(
    "/fpvr-5",
    response_model=FPVR5RequestListResponse,
    summary="List official FPVR-5 CV Alerts requests",
    responses=_LIST_ERROR_RESPONSES,
)
def list_fpvr5_requests(
    request: Request, query: FPVRRequestListQuery = Depends(_list_query)
):
    """Return FPVR-5 request log rows matching optional filters."""
    return _list_typed(request, query, ReportCode.FPVR_5, _to_fpvr5, FPVR5RequestListResponse)


@router.get(
    "/fpvr-5/{request_id}",
    response_model=FPVR5RequestAccepted,
    summary="Get an official FPVR-5 CV Alerts request",
    responses=_GET_ERROR_RESPONSES,
)
def get_fpvr5_request(request: Request, request_id: str, response: Response):
    """Return the same typed body as POST /v1/requests/fpvr-5."""
    return _get_typed(request, request_id, response, ReportCode.FPVR_5, _to_fpvr5)


@router.post(
    "/fpvr-6",
    response_model=FPVR6RequestAccepted,
    status_code=201,
    summary="Open an official FPVR-6 Human Capital request",
    responses=_ERROR_RESPONSES,
)
def create_fpvr6_request(request: Request, body: FPVR6RequestCreate, response: Response):
    """Create an FPVR-6 request. Report code is implied by the path."""
    return _create_typed(request, body, response, ReportCode.FPVR_6, _to_fpvr6)


@router.get(
    "/fpvr-6",
    response_model=FPVR6RequestListResponse,
    summary="List official FPVR-6 Human Capital requests",
    responses=_LIST_ERROR_RESPONSES,
)
def list_fpvr6_requests(
    request: Request, query: FPVRRequestListQuery = Depends(_list_query)
):
    """Return FPVR-6 request log rows matching optional filters."""
    return _list_typed(request, query, ReportCode.FPVR_6, _to_fpvr6, FPVR6RequestListResponse)


@router.get(
    "/fpvr-6/{request_id}",
    response_model=FPVR6RequestAccepted,
    summary="Get an official FPVR-6 Human Capital request",
    responses=_GET_ERROR_RESPONSES,
)
def get_fpvr6_request(request: Request, request_id: str, response: Response):
    """Return the same typed body as POST /v1/requests/fpvr-6."""
    return _get_typed(request, request_id, response, ReportCode.FPVR_6, _to_fpvr6)


@router.post(
    "/fpvr-7",
    response_model=FPVR7RequestAccepted,
    status_code=201,
    summary="Open an official FPVR-7 Favorable to Onboard request",
    responses=_ERROR_RESPONSES,
)
def create_fpvr7_request(request: Request, body: FPVR7RequestCreate, response: Response):
    """Create an FPVR-7 request. Report code is implied by the path."""
    return _create_typed(request, body, response, ReportCode.FPVR_7, _to_fpvr7)


@router.get(
    "/fpvr-7",
    response_model=FPVR7RequestListResponse,
    summary="List official FPVR-7 Favorable to Onboard requests",
    responses=_LIST_ERROR_RESPONSES,
)
def list_fpvr7_requests(
    request: Request, query: FPVRRequestListQuery = Depends(_list_query)
):
    """Return FPVR-7 request log rows matching optional filters."""
    return _list_typed(request, query, ReportCode.FPVR_7, _to_fpvr7, FPVR7RequestListResponse)


@router.get(
    "/fpvr-7/{request_id}",
    response_model=FPVR7RequestAccepted,
    summary="Get an official FPVR-7 Favorable to Onboard request",
    responses=_GET_ERROR_RESPONSES,
)
def get_fpvr7_request(request: Request, request_id: str, response: Response):
    """Return the same typed body as POST /v1/requests/fpvr-7."""
    return _get_typed(request, request_id, response, ReportCode.FPVR_7, _to_fpvr7)
