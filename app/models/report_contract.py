"""Shared FPVR catalog schemas and optional known-section row models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IdentitySectionRow(BaseModel):
    """Public identity section row (ssn omitted)."""

    model_config = ConfigDict(extra="forbid")

    first_name: str
    last_name: str
    date_of_birth: datetime | None = None
    place_of_birth: str | None = None
    sex: str | None = None
    citizenship: str | None = None
    marital_status: str | None = None
    updated_ts: str | None = None
    record_version: str | None = None


class StatusSectionRow(BaseModel):
    """Public status section row (ssn omitted)."""

    model_config = ConfigDict(extra="forbid")

    organization_code: str | None = None
    position_title: str | None = None
    duty_location: str | None = None
    risk_tier: str | None = None
    eligibility_level: str | None = None
    status_code: str | None = None
    status_effective_date: str | None = None
    updated_ts: str | None = None
    record_version: str | None = None


class CheckSectionRow(BaseModel):
    """Public check section row (ssn omitted)."""

    model_config = ConfigDict(extra="forbid")

    check_id: str | None = None
    location_code: str | None = None
    check_type: str | None = None
    result_code: str | None = None
    result_score: str | None = None
    checked_ts: str | None = None
    load_seq: str | None = None


class ActivitySectionRow(BaseModel):
    """Public activity section row (ssn omitted)."""

    model_config = ConfigDict(extra="forbid")

    activity_id: str | None = None
    location_code: str | None = None
    activity_type: str | None = None
    detail: str | None = None
    event_ts: str | None = None
    load_seq: str | None = None


class SignalSectionRow(BaseModel):
    """Public signal section row (ssn omitted)."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str | None = None
    location_code: str | None = None
    signal_type: str | None = None
    severity: str | None = None
    signal_ts: str | None = None
    load_seq: str | None = None


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
    """Per-report payload contract nested in request.report."""

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
