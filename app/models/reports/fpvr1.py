"""Typed response models for the FPVR-1 Application Bundle API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.reports.registry import register_report
from app.models.report_contract import SECTION_ROW_MODELS


class FPVR1ReportData(BaseModel):
    """FPVR-1 ``data`` sections: identity, status, and check."""

    identity: list[SECTION_ROW_MODELS["identity"]] = Field(default_factory=list)
    status: list[SECTION_ROW_MODELS["status"]] = Field(default_factory=list)
    check: list[SECTION_ROW_MODELS["check"]] = Field(default_factory=list)

@register_report("FPVR-1")
class FPVR1RequestAccepted(OfficialRequestAccepted[FPVR1ReportData]):
    """FPVR-1 request envelope. ``report`` is set when status is ready."""
