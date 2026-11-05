"""Shared FPVR catalog schemas. Source row models are generated at startup."""

from __future__ import annotations

from pydantic import BaseModel

from app.models.sources.registry import ready_source_models

SECTION_ROW_MODELS: dict[str, type[BaseModel]] = ready_source_models()
IdentitySectionRow = SECTION_ROW_MODELS["identity"]


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
