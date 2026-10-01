"""Pydantic request/response models.

Models define the API contract only. They hold no persistence or HTTP logic so
they can be shared by routes and services without circular dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.models.subject_identity import (
    SubjectIdentity,
    SubjectIdentityListResponse,
    SubjectIdentitySearch,
)


class RecordStatus(str, Enum):
    """Lifecycle state of a sample record.

    Attributes:
        draft: Created but not yet active.
        active: In use.
        archived: Retained but no longer in use.
    """

    draft = "draft"
    active = "active"
    archived = "archived"


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


class RecordCreate(BaseModel):
    """Request body for creating a sample record.

    Attributes:
        name: Display name, trimmed of surrounding whitespace.
        description: Free-text description.
        status: Initial lifecycle state.
        tags: Tags, de-duplicated case-insensitively.
        metadata: Arbitrary key/value metadata.
    """

    name: str = Field(..., min_length=1, max_length=200, examples=["Sample DCSA record"])
    description: str = Field(default="", max_length=2000)
    status: RecordStatus = RecordStatus.draft
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        """Trim surrounding whitespace from the record name.

        Args:
            v: Raw name value.

        Returns:
            The trimmed name.
        """
        return v.strip()

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, v: list[str]) -> list[str]:
        """Drop blank tags and remove case-insensitive duplicates.

        Args:
            v: Raw tag values.

        Returns:
            Trimmed, de-duplicated tags in their original order.
        """
        out: list[str] = []
        seen: set[str] = set()
        for raw in v or []:
            t = (raw or "").strip()
            if not t:
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
        return out


class RecordUpdate(BaseModel):
    """Partial update for a sample record. Only fields that are set are applied.

    Attributes:
        name: New display name.
        description: New description.
        status: New lifecycle state.
        tags: Replacement tag list.
        metadata: Replacement metadata.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: RecordStatus | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class Record(BaseModel):
    """A stored sample record.

    Attributes:
        id: Unique record identifier (UUID4).
        name: Display name.
        description: Free-text description.
        status: Lifecycle state.
        tags: Record tags.
        metadata: Arbitrary key/value metadata.
        created_at: UTC creation time.
        updated_at: UTC time of the last update.
        created_by: Identity of the caller who created the record, if known.
    """

    id: str
    name: str
    description: str = ""
    status: RecordStatus = RecordStatus.draft
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None

    @staticmethod
    def new(body: RecordCreate, *, created_by: str | None = None) -> "Record":
        """Build a new record from a create request.

        Args:
            body: Validated create request.
            created_by: Identity of the caller creating the record.

        Returns:
            A new record with a generated id and matching created/updated times.
        """
        now = datetime.now(timezone.utc)
        return Record(
            id=str(uuid4()),
            name=body.name,
            description=body.description,
            status=body.status,
            tags=list(body.tags),
            metadata=dict(body.metadata),
            created_at=now,
            updated_at=now,
            created_by=created_by,
        )


class RecordListResponse(BaseModel):
    """A page of sample records.

    Attributes:
        items: Records in the requested page.
        total: Total number of records matching the filters, across all pages.
    """

    items: list[Record]
    total: int


class ErrorResponse(BaseModel):
    """Standard error body returned with non-2xx responses.

    Attributes:
        detail: Human-readable error message.
    """

    detail: str


__all__ = [
    "ErrorResponse",
    "HealthResponse",
    "MeResponse",
    "Record",
    "RecordCreate",
    "RecordListResponse",
    "RecordStatus",
    "RecordUpdate",
    "SubjectIdentity",
    "SubjectIdentityListResponse",
    "SubjectIdentitySearch",
]
