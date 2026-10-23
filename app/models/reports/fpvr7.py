"""Typed response models for the FPVR-7 Favorable to Onboard API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import StatusSectionRow


class FPVR7ReportData(BaseModel):
    """FPVR-7 ``data`` sections: status."""

    status: list[StatusSectionRow] = Field(default_factory=list)


class FPVR7RequestAccepted(OfficialRequestAccepted[FPVR7ReportData]):
    """FPVR-7 request envelope. ``report`` is set when status is ready."""
