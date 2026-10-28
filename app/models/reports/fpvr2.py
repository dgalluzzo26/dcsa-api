"""Typed response models for the FPVR-2 Investigation Summary API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import SECTION_ROW_MODELS
from app.models.reports.registry import register_report


class FPVR2ReportData(BaseModel):
    """FPVR-2 ``data`` sections: activity and check."""

    activity: list[SECTION_ROW_MODELS["activity"]] = Field(default_factory=list)
    check: list[SECTION_ROW_MODELS["check"]] = Field(default_factory=list)

@register_report("FPVR-2")
class FPVR2RequestAccepted(OfficialRequestAccepted[FPVR2ReportData]):
    """FPVR-2 request envelope. ``report`` is set when status is ready."""
