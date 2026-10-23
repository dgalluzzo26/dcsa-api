"""Typed response models for the FPVR-3 Adjudication Summary API."""

from pydantic import BaseModel, Field

from app.models.fpvr import OfficialRequestAccepted
from app.models.report_contract import CheckSectionRow, StatusSectionRow


class FPVR3ReportData(BaseModel):
    """FPVR-3 ``data`` sections: status and check."""

    status: list[StatusSectionRow] = Field(default_factory=list)
    check: list[CheckSectionRow] = Field(default_factory=list)


class FPVR3RequestAccepted(OfficialRequestAccepted[FPVR3ReportData]):
    """FPVR-3 request envelope. ``report`` is set when status is ready."""
