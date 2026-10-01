"""HTTP routes — thin controllers over services."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

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
from app.services import RecordNotFoundError, get_record_service

router = APIRouter()


def _caller_identity(request: Request) -> str | None:
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
    return get_record_service().create(body, created_by=_caller_identity(request))


@router.get(
    "/records/{record_id}",
    response_model=Record,
    tags=["records"],
    summary="Get a record by id",
    responses={404: {"model": ErrorResponse}},
)
def get_record(record_id: str) -> Record:
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
    try:
        return get_record_service().update(record_id, body)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Record not found: {record_id}") from e


@router.delete(
    "/records/{record_id}",
    status_code=204,
    tags=["records"],
    summary="Delete a record",
    responses={404: {"model": ErrorResponse}},
)
def delete_record(record_id: str) -> None:
    try:
        get_record_service().delete(record_id)
    except RecordNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Record not found: {record_id}") from e
