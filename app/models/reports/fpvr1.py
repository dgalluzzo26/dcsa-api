"""Typed response models for the FPVR-1 Application Bundle API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import CheckSectionRow, IdentitySectionRow, StatusSectionRow


class FPVR1ReportData(BaseModel):
    """FPVR-1 ``data`` sections: identity, status, and check."""

    identity: list[IdentitySectionRow] = Field(default_factory=list)
    status: list[StatusSectionRow] = Field(default_factory=list)
    check: list[CheckSectionRow] = Field(default_factory=list)


class FPVR1RequestAccepted(OfficialRequestAccepted[FPVR1ReportData]):
    """FPVR-1 request envelope. ``report`` is set when status is ready."""
