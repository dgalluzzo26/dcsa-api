"""Typed response models for the FPVR-4 CV Summary API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import IdentitySectionRow, StatusSectionRow


class FPVR4ReportData(BaseModel):
    """FPVR-4 ``data`` sections: identity and status."""

    identity: list[IdentitySectionRow] = Field(default_factory=list)
    status: list[StatusSectionRow] = Field(default_factory=list)


class FPVR4RequestAccepted(OfficialRequestAccepted[FPVR4ReportData]):
    """FPVR-4 request envelope. ``report`` is set when status is ready."""
