"""Pydantic request/response models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class RecordStatus(str, Enum):
    draft = "draft"
    active = "active"
    archived = "archived"


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    environment: str
    version: str


class MeResponse(BaseModel):
    """Caller identity when running inside Databricks Apps (forwarded headers)."""

    identity: str | None = None
    email: str | None = None
    user: str | None = None
    source: str = "none"


class RecordCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, examples=["Sample DCSA record"])
    description: str = Field(default="", max_length=2000)
    status: RecordStatus = RecordStatus.draft
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, v: list[str]) -> list[str]:
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
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: RecordStatus | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class Record(BaseModel):
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
    items: list[Record]
    total: int


class ErrorResponse(BaseModel):
    detail: str
