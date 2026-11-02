"""Map FPVR-6 warehouse rows onto agency DTOs.

Databricks column names stay in ``config.yaml``. This module is the only place
that translates those columns into FPVR-6 JSON. Agency-specific masking still
belongs in Unity Catalog (ABAC / column masks); this mapper does not branch on
caller identity.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.models.dto.fpvr6 import IdentityDto, StatusDto

_FPVR6 = "fpvr6"


def maybe_map_accepted(report_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Return ``payload`` with FPVR-6 ``report`` rewritten as DTOs.

    Other report codes are returned unchanged so existing column-shaped
    envelopes keep working.

    Args:
        report_code: Normalized report path segment (for example ``fpvr6``).
        payload: ``OfficialRequestAccepted.model_dump()`` body.

    Returns:
        The same dict, or a copy whose ``report.subject`` / ``report.data``
        use agency field names.
    """
    if report_code != _FPVR6:
        return payload
    report = payload.get("report")
    if not report:
        return payload
    mapped = dict(payload)
    mapped["report"] = map_report(report)
    return mapped


def map_report(report: dict[str, Any]) -> dict[str, Any]:
    """Rewrite one nested report object from warehouse columns to DTOs.

    Args:
        report: Assembler-shaped report with ``subject`` and ``data``.

    Returns:
        Report dict using ``IdentityDto`` / ``StatusDto`` field names.
    """
    data = report.get("data") or {}
    return {
        "code": report.get("code"),
        "title": report.get("title"),
        "subject": map_identity(report.get("subject") or {}).model_dump(mode="json"),
        "data": {
            "identity": [
                map_identity(row).model_dump(mode="json") for row in data.get("identity") or []
            ],
            "status": [
                map_status(row).model_dump(mode="json") for row in data.get("status") or []
            ],
        },
    }


def map_identity(row: dict[str, Any]) -> IdentityDto:
    """Map a ``subject_identity`` (or identity-section) row to ``IdentityDto``.

    Args:
        row: Warehouse-oriented dict (``FIRST_NAME``, …). DTO keys are also
            accepted so catalog samples can be mapped twice safely.

    Returns:
        Agency identity DTO. ``SSN``, ``UPDATED_TS``, and ``RECORD_VERSION``
        are dropped.
    """
    return IdentityDto(
        first_name=_pick(row, "first_name", "FIRST_NAME") or "",
        last_name=_pick(row, "last_name", "LAST_NAME") or "",
        date_of_birth=_as_date(_pick(row, "date_of_birth", "DATE_OF_BIRTH")),
        place_of_birth=_pick(row, "place_of_birth", "PLACE_OF_BIRTH"),
        sex=_pick(row, "sex", "SEX"),
        citizenship=_pick(row, "citizenship", "CITIZENSHIP"),
        marital_status=_pick(row, "marital_status", "MARITAL_STATUS"),
    )


def map_status(row: dict[str, Any]) -> StatusDto:
    """Map a ``subject_status`` row to ``StatusDto``.

    Args:
        row: Warehouse-oriented dict (``ORG_CODE``, …).

    Returns:
        Agency status DTO. Lake metadata columns are dropped.
    """
    return StatusDto(
        organization_code=_pick(row, "organization_code", "ORG_CODE"),
        position_title=_pick(row, "position_title", "POSITION_TITLE"),
        duty_location=_pick(row, "duty_location", "DUTY_LOCATION"),
        risk_tier=_pick(row, "risk_tier", "RISK_TIER"),
        eligibility_level=_pick(row, "eligibility_level", "ELIGIBILITY_LEVEL"),
        status_code=_pick(row, "status_code", "STATUS_CODE"),
        status_effective_date=_pick(row, "status_effective_date", "STATUS_EFFECTIVE_DATE"),
    )


def _pick(row: dict[str, Any], dto_key: str, column: str) -> Any:
    """Return the DTO value if already mapped, else the warehouse column."""
    if dto_key in row:
        return row[dto_key]
    return row.get(column)


def _as_date(value: Any) -> date | None:
    """Coerce warehouse timestamps/strings to a calendar date."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    return date.fromisoformat(text[:10])
