"""Build typed request-accepted models from ``config.yaml`` reports."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.core.config import get_settings
from app.models.fpvr import RequestStatusValue
from app.models.report_contract import SECTION_ROW_MODELS, IdentitySectionRow


def _pascal_prefix(report_code: str) -> str:
    """Turn a report code into a Pydantic class-name prefix.

    Args:
        report_code: YAML report key (for example ``FPVR-Application-Bundle``).

    Returns:
        Concatenated alphanumeric segments (``FPVRApplicationBundle``).
    """
    return "".join(
        part[:1].upper() + part[1:]
        for part in report_code.replace("-", "_").split("_")
        if part
    )


def _build_request_accepted(report_code: str) -> type[BaseModel]:
    """Create the OpenAPI envelope for one configured report.

    Args:
        report_code: YAML report key.

    Returns:
        A ``*RequestAccepted`` model whose ``data`` fields match YAML sections.

    Raises:
        ValueError: If a section source has no row model.
        KeyError: If ``report_code`` is not configured.
    """
    settings = get_settings()
    report = settings.reports[report_code]
    prefix = _pascal_prefix(report_code)
    data_fields: dict[str, tuple[type, object]] = {}
    for section_name, section in report.sections.items():
        row_model = SECTION_ROW_MODELS.get(section.source)
        if row_model is None:
            raise ValueError(
                f"Report {report_code} section {section_name!r} source "
                f"{section.source!r} has no row model in SECTION_ROW_MODELS"
            )
        data_fields[section_name] = (list[row_model], Field(default_factory=list))
    data_model = create_model(
        f"{prefix}ReportData",
        __config__=ConfigDict(extra="forbid"),
        **data_fields,
    )
    report_model = create_model(
        f"{prefix}Report",
        __config__=ConfigDict(extra="forbid"),
        code=(Literal[report_code], report_code),
        title=(str, report.name),
        subject=(IdentitySectionRow, ...),
        data=(data_model, ...),
    )
    return create_model(
        f"{prefix}RequestAccepted",
        __config__=ConfigDict(extra="forbid"),
        request_id=(str, ...),
        status=(RequestStatusValue, ...),
        requested_at=(str, ...),
        requested_by=(str | None, None),
        resolution_method=(str, ...),
        report=(report_model | None, None),
    )


@lru_cache
def ready_report_models() -> dict[str, type[BaseModel]]:
    """Return ``{report_code: RequestAccepted}`` for every configured report.

    Models are built from YAML sections and ``SECTION_ROW_MODELS``. Missing row
    models fail startup.

    Returns:
        Mapping of YAML report code to its generated envelope model.
    """
    return {
        report_code: _build_request_accepted(report_code)
        for report_code in get_settings().reports
    }
