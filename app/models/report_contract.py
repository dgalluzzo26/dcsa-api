"""Shared FPVR catalog schemas and optional known-section row models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IdentitySectionRow(BaseModel):
    """Public identity section row (SSN omitted)."""

    model_config = ConfigDict(extra="forbid")

    FIRST_NAME: str
    LAST_NAME: str
    DATE_OF_BIRTH: datetime | None = None
    PLACE_OF_BIRTH: str | None = None
    SEX: str | None = None
    CITIZENSHIP: str | None = None
    MARITAL_STATUS: str | None = None
    UPDATED_TS: str | None = None
    RECORD_VERSION: str | None = None


class StatusSectionRow(BaseModel):
    """Public status section row (SSN omitted)."""

    model_config = ConfigDict(extra="forbid")

    ORG_CODE: str | None = None
    POSITION_TITLE: str | None = None
    DUTY_LOCATION: str | None = None
    RISK_TIER: str | None = None
    ELIGIBILITY_LEVEL: str | None = None
    STATUS_CODE: str | None = None
    STATUS_EFFECTIVE_DATE: str | None = None
    UPDATED_TS: str | None = None
    RECORD_VERSION: str | None = None


class CheckSectionRow(BaseModel):
    """Public check section row (SSN omitted)."""

    model_config = ConfigDict(extra="forbid")

    CHECK_ID: str | None = None
    LOCATION_CODE: str | None = None
    CHECK_TYPE: str | None = None
    RESULT_CODE: str | None = None
    RESULT_SCORE: str | None = None
    CHECKED_TS: str | None = None
    LOAD_SEQ: str | None = None


class ActivitySectionRow(BaseModel):
    """Public activity section row (SSN omitted)."""

    model_config = ConfigDict(extra="forbid")

    ACTIVITY_ID: str | None = None
    LOCATION_CODE: str | None = None
    ACTIVITY_TYPE: str | None = None
    DETAIL: str | None = None
    EVENT_TS: str | None = None
    LOAD_SEQ: str | None = None


class SignalSectionRow(BaseModel):
    """Public signal section row (SSN omitted)."""

    model_config = ConfigDict(extra="forbid")

    SIGNAL_ID: str | None = None
    LOCATION_CODE: str | None = None
    SIGNAL_TYPE: str | None = None
    SEVERITY: str | None = None
    SIGNAL_TS: str | None = None
    LOAD_SEQ: str | None = None


SECTION_ROW_MODELS: dict[str, type[BaseModel]] = {
    "identity": IdentitySectionRow,
    "status": StatusSectionRow,
    "check": CheckSectionRow,
    "activity": ActivitySectionRow,
    "signal": SignalSectionRow,
}


class CatalogField(BaseModel):
    """One JSON field in a report section row."""

    name: str
    type: str
    nullable: bool = True


class CatalogScenario(BaseModel):
    """One HTTP outcome for an API."""

    id: str
    http_status: int
    summary: str
    request: dict | None = None
    response: dict


class CatalogApi(BaseModel):
    """One of the three FPVR HTTP APIs (plus token)."""

    id: str
    method: str
    path: str
    auth: str
    summary: str
    request_body: dict | None = None
    scenarios: list[CatalogScenario]


class CatalogReport(BaseModel):
    """Per-report GET /response payload contract."""

    report_code: str
    title: str
    sources: list[str]
    tables: list[str]
    readiness: str
    data_fields: dict[str, list[CatalogField]]
    example_response: dict


class ApiCatalog(BaseModel):
    """Machine-readable help for callers of the FPVR APIs."""

    title: str
    version: str
    apis: list[CatalogApi]
    reports: list[CatalogReport]
    notes: list[str]
