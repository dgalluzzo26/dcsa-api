"""Typed response models for the mock Awards report type."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import AwardsSectionRow, CheckSectionRow


class AWARDSReportData(BaseModel):
    """Awards ``data`` sections: awards and check."""

    awards: list[AwardsSectionRow] = Field(default_factory=list)
    check: list[CheckSectionRow] = Field(default_factory=list)


class AWARDSRequestAccepted(OfficialRequestAccepted[AWARDSReportData]):
    """Awards request envelope. ``report`` is set when status is ready."""
