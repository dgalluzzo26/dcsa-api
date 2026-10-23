"""Typed response models for the FPVR-2 Investigation Summary API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import ActivitySectionRow, CheckSectionRow


class FPVR2ReportData(BaseModel):
    """FPVR-2 ``data`` sections: activity and check."""

    activity: list[ActivitySectionRow] = Field(default_factory=list)
    check: list[CheckSectionRow] = Field(default_factory=list)


class FPVR2RequestAccepted(OfficialRequestAccepted[FPVR2ReportData]):
    """FPVR-2 request envelope. ``report`` is set when status is ready."""
