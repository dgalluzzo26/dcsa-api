"""Typed response models for the FPVR-6 Human Capital API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import SECTION_ROW_MODELS
from app.models.reports.registry import register_report

class FPVR6ReportData(BaseModel):
    """FPVR-6 ``data`` sections: identity and status."""

    identity: list[SECTION_ROW_MODELS["identity"]] = Field(default_factory=list)
    status: list[SECTION_ROW_MODELS["status"]] = Field(default_factory=list)

@register_report("FPVR-6")
class FPVR6RequestAccepted(OfficialRequestAccepted[FPVR6ReportData]):
    """FPVR-6 request envelope. ``report`` is set when status is ready."""
