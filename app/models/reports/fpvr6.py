"""Typed response models for the FPVR-6 Human Capital API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import IdentitySectionRow, StatusSectionRow


class FPVR6ReportData(BaseModel):
    """FPVR-6 ``data`` sections: identity and status."""

    identity: list[IdentitySectionRow] = Field(default_factory=list)
    status: list[StatusSectionRow] = Field(default_factory=list)


class FPVR6RequestAccepted(OfficialRequestAccepted[FPVR6ReportData]):
    """FPVR-6 request envelope. ``report`` is set when status is ready."""
