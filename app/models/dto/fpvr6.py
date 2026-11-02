"""FPVR-6 Human Capital DTOs — the agency JSON contract.

Field names here are independent of Unity Catalog columns. Lake metadata
(``UPDATED_TS``, ``RECORD_VERSION``) and join keys (``SSN``) are not part of
this contract. Column mapping lives in ``app.services.dto_fpvr6``.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class IdentityDto(BaseModel):
    """Public identity fields for FPVR-6. No SSN, no lake metadata."""

    model_config = ConfigDict(extra="forbid")

    first_name: str
    last_name: str
    date_of_birth: date | None = None
    place_of_birth: str | None = None
    sex: str | None = None
    citizenship: str | None = None
    marital_status: str | None = None


class StatusDto(BaseModel):
    """Public employment/eligibility fields for FPVR-6."""

    model_config = ConfigDict(extra="forbid")

    organization_code: str | None = None
    position_title: str | None = None
    duty_location: str | None = None
    risk_tier: str | None = None
    eligibility_level: str | None = None
    status_code: str | None = None
    status_effective_date: str | None = None


class FPVR6ReportData(BaseModel):
    """FPVR-6 ``data`` sections using agency field names."""

    identity: list[IdentityDto] = Field(default_factory=list)
    status: list[StatusDto] = Field(default_factory=list)
