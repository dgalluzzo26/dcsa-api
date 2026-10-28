"""Typed response models for the FPVR-7 Favorable to Onboard API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import SECTION_ROW_MODELS
from app.models.reports.registry import register_report


class FPVR7ReportData(BaseModel):
    """FPVR-7 ``data`` sections: status."""

    status: list[SECTION_ROW_MODELS["status"]] = Field(default_factory=list)

@register_report("FPVR-7")
class FPVR7RequestAccepted(OfficialRequestAccepted[FPVR7ReportData]):
    """FPVR-7 request envelope. ``report`` is set when status is ready."""
