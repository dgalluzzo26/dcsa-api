"""Typed response models for the FPVR-3 Adjudication Summary API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import SECTION_ROW_MODELS
from app.models.reports.registry import register_report


class FPVR3ReportData(BaseModel):
    """FPVR-3 ``data`` sections: status and check."""

    status: list[SECTION_ROW_MODELS["status"]] = Field(default_factory=list)
    check: list[SECTION_ROW_MODELS["check"]] = Field(default_factory=list)

@register_report("FPVR-3")
class FPVR3RequestAccepted(OfficialRequestAccepted[FPVR3ReportData]):
    """FPVR-3 request envelope. ``report`` is set when status is ready."""
