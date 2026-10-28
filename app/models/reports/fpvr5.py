"""Typed response models for the FPVR-5 CV Alerts API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import SECTION_ROW_MODELS
from app.models.reports.registry import register_report


class FPVR5ReportData(BaseModel):
    """FPVR-5 ``data`` sections: signal."""

    signal: list[SECTION_ROW_MODELS["signal"]] = Field(default_factory=list)

@register_report("FPVR-5")
class FPVR5RequestAccepted(OfficialRequestAccepted[FPVR5ReportData]):
    """FPVR-5 request envelope. ``report`` is set when status is ready."""
