"""Shared FPVR catalog schemas and section-row models built from YAML sources."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, create_model

from app.core.config import SourceConfig, get_settings

_FIELD_TYPES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "date": date,
    "datetime": datetime,
}


def build_section_row_models(
    sources: dict[str, SourceConfig],
) -> dict[str, type[BaseModel]]:
    """Build one Pydantic row model per configured source.

    Public columns (``columns`` minus ``omit_from_output``) become model fields.
    YAML ``fields`` supply type and nullability; unspecified public columns are
    nullable strings.

    Args:
        sources: Validated source configs keyed by source name.

    Returns:
        Mapping of source name to generated row model.
    """
    models: dict[str, type[BaseModel]] = {}
    for name, source in sources.items():
        omit = set(source.omit_from_output)
        field_defs: dict[str, Any] = {}
        for col in source.columns:
            if col in omit:
                continue
            spec = source.fields.get(col)
            py_type = _FIELD_TYPES[spec.type] if spec is not None else str
            nullable = True if spec is None else spec.nullable
            if nullable:
                field_defs[col] = (py_type | None, None)
            else:
                field_defs[col] = (py_type, ...)
        models[name] = create_model(
            f"{name.title()}SectionRow",
            __config__=ConfigDict(extra="forbid"),
            **field_defs,
        )
    return models


SECTION_ROW_MODELS: dict[str, type[BaseModel]] = build_section_row_models(
    get_settings().sources
)

IdentitySectionRow = SECTION_ROW_MODELS["identity"]
StatusSectionRow = SECTION_ROW_MODELS["status"]
CheckSectionRow = SECTION_ROW_MODELS["check"]
ActivitySectionRow = SECTION_ROW_MODELS["activity"]
SignalSectionRow = SECTION_ROW_MODELS["signal"]


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
