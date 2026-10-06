"""Subject identity HTTP routes.

Thin controllers over ``SubjectIdentityService``: extract the caller's token,
delegate to the service, and translate domain errors into HTTP status codes.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import ValidationError

from app.core.http_logging import gateway_error, log_failure
from app.core.obo import get_obo_token
from app.core.sql import WarehouseNotConfiguredError
from app.models import ErrorResponse, SubjectIdentityListResponse, SubjectIdentitySearch
from app.services import SubjectIdentityQueryError, get_subject_identity_service

router = APIRouter(prefix="/subject-identities", tags=["subject-identity"])

_ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _search(request: Request, query: SubjectIdentitySearch) -> SubjectIdentityListResponse:
    """Run a search as the calling user and map service errors to HTTP errors.

    Args:
        request: Incoming request carrying the caller's access token.
        query: Validated search filters.

    Returns:
        Matching subject identities.

    Raises:
        HTTPException: 401 if no user token is present, 503 if no SQL warehouse
            is configured, or 502 if the warehouse query fails.
    """
    token = get_obo_token(request)
    try:
        return get_subject_identity_service().search(query, user_token=token)
    except WarehouseNotConfiguredError as e:
        log_failure(request, e, step="warehouse")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except SubjectIdentityQueryError as e:
        raise gateway_error(
            request, e, detail="Subject identity query failed", step="identity_sql"
        ) from e


@router.get(
    "",
    response_model=SubjectIdentityListResponse,
    summary="Search subject identities (OBO SQL)",
    responses=_ERROR_RESPONSES,
)
def list_subject_identities(
    request: Request,
    ssn: str | None = Query(default=None, description="Social Security Number"),
    first_name: str | None = Query(default=None),
    last_name: str | None = Query(default=None),
    date_of_birth: date | None = Query(default=None, description="YYYY-MM-DD"),
    limit: int = Query(default=50, ge=1, le=200),
) -> SubjectIdentityListResponse:
    """Search subject identities using query-string filters.

    At least one of `ssn`, `first_name`, `last_name` or `date_of_birth` is required.
    \f
    Args:
        request: Incoming request carrying the caller's access token.
        ssn: Social Security Number filter.
        first_name: First name filter, case-insensitive.
        last_name: Last name filter, case-insensitive.
        date_of_birth: Date of birth filter.
        limit: Maximum number of rows to return.

    Returns:
        Matching subject identities.

    Raises:
        HTTPException: 400 if no identity filter is provided, plus the errors
            raised by ``_search``.
    """
    try:
        query = SubjectIdentitySearch(
            ssn=ssn,
            first_name=first_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            limit=limit,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one of ssn, first_name, last_name, date_of_birth",
        ) from e
    return _search(request, query)


@router.post(
    "/search",
    response_model=SubjectIdentityListResponse,
    summary="Search subject identities (OBO SQL, JSON body)",
    responses=_ERROR_RESPONSES,
)
def search_subject_identities(
    request: Request, body: SubjectIdentitySearch
) -> SubjectIdentityListResponse:
    """Search subject identities using a JSON body.

    Prefer this over the GET endpoint so SSNs are not written to URLs and access logs.
    \f
    Args:
        request: Incoming request carrying the caller's access token.
        body: Search filters. Validation (422) runs before this handler.

    Returns:
        Matching subject identities.

    Raises:
        HTTPException: Errors raised by ``_search``.
    """
    return _search(request, body)
