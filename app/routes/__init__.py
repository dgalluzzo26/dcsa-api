"""HTTP routes — thin controllers over services.

Route handlers parse HTTP input, call a service, and map domain exceptions to
HTTP status codes. Business logic belongs in ``app.services``. Domain routers
live in their own modules and are included here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app import __version__
from app.core.config import get_settings
from app.models import (
    ErrorResponse,
    HealthResponse,
    MeResponse,
    Record,
    RecordCreate,
    RecordListResponse,
    RecordStatus,
    RecordUpdate,
)
from app.routes.subject_identity import router as subject_identity_router
from app.services import RecordNotFoundError, get_record_service

router = APIRouter()
router.include_router(subject_identity_router)


def _caller_identity(request: Request) -> str | None:
    """Return the best available caller identifier from forwarded headers.

    Args:
        request: Incoming HTTP request.

    Returns:
        The forwarded email, preferred username, or user id, in that order of
        preference, or ``None`` if none is present.
    """
    email = (request.headers.get("x-forwarded-email") or "").strip()
    preferred = (request.headers.get("x-forwarded-preferred-username") or "").strip()
    user = (request.headers.get("x-forwarded-user") or "").strip()
    return email or preferred or user or None


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


@router.get(
    "/records",
    response_model=RecordListResponse,
    tags=["records"],
    summary="List records",
)
def list_records(
    status: RecordStatus | None = Query(default=None),
    q: str | None = Query(default=None, description="Search name/description"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RecordListResponse:
    """List records with optional filtering and pagination.
    \f
    Args:
        status: Only return records in this state.
        q: Case-insensitive search over name and description.
        limit: Page size.
        offset: Number of records to skip.

    Returns:
        The requested page and the total match count.
    """
    items, total = get_record_service().list(status=status, q=q, limit=limit, offset=offset)
    return RecordListResponse(items=items, total=total)


@router.post(
    "/records",
    response_model=Record,
    status_code=201,
    tags=["records"],
    summary="Create a record",
    responses={400: {"model": ErrorResponse}},
)
def create_record(request: Request, body: RecordCreate) -> Record:
    """Create a record attributed to the calling user.
    \f
    Args:
        request: Incoming request, used to identify the caller.
        body: Record to create.

    Returns:
        The created record.
    """
    return get_record_service().create(body, created_by=_caller_identity(request))


@router.get(
    "/records/{record_id}",
    response_model=Record,
    tags=["records"],
    summary="Get a record by id",
    responses={404: {"model": ErrorResponse}},
)
def get_record(record_id: str) -> Record:
    """Fetch a single record.
    \f
    Args:
        record_id: Record identifier.

    Returns:
        The matching record.

    Raises:
        HTTPException: 404 if the record does not exist.
    """
    try:
        return get_record_service().get(record_id)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Record not found: {record_id}") from e


@router.patch(
    "/records/{record_id}",
    response_model=Record,
    tags=["records"],
    summary="Update a record",
    responses={404: {"model": ErrorResponse}},
)
def update_record(record_id: str, body: RecordUpdate) -> Record:
    """Partially update a record. Only fields present in the body are changed.
    \f
    Args:
        record_id: Record identifier.
        body: Fields to change.

    Returns:
        The updated record.

    Raises:
        HTTPException: 404 if the record does not exist.
    """
    try:
        return get_record_service().update(record_id, body)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Record not found: {record_id}") from e


@router.delete(
    "/records/{record_id}",
    status_code=204,
    response_model=None,
    response_class=Response,
    tags=["records"],
    summary="Delete a record",
    responses={404: {"model": ErrorResponse}},
)
def delete_record(record_id: str) -> None:
    """Delete a record.
    \f
    Args:
        record_id: Record identifier.

    Raises:
        HTTPException: 404 if the record does not exist.
    """
    try:
        get_record_service().delete(record_id)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Record not found: {record_id}") from e
