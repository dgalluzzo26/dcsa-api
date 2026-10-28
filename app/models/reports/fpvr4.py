"""Typed response models for the FPVR-4 CV Summary API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import SECTION_ROW_MODELS
from app.models.reports.registry import register_report


class FPVR4ReportData(BaseModel):
    """FPVR-4 ``data`` sections: identity and status."""

    identity: list[SECTION_ROW_MODELS["identity"]] = Field(default_factory=list)
    status: list[SECTION_ROW_MODELS["status"]] = Field(default_factory=list)

@register_report("FPVR-4")
class FPVR4RequestAccepted(OfficialRequestAccepted[FPVR4ReportData]):
    """FPVR-4 request envelope. ``report`` is set when status is ready."""
