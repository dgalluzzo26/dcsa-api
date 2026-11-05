"""Typed request and response models for the FPVR-1 Application Bundle API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.fpvr import (
    FPVRSubjectCreate,
    REPORT_TITLES,
    ReportCode,
    RequestSource,
    RequestStatusValue,
)
from app.models.report_contract import CheckSectionRow, IdentitySectionRow, StatusSectionRow


class FPVR1RequestCreate(FPVRSubjectCreate):
    """Body for opening an FPVR-1 request. Report code is implied by the route."""


class FPVR1ReportData(BaseModel):
    """FPVR-1 ``data`` sections: identity, status, and check."""

    identity: list[IdentitySectionRow] = Field(default_factory=list)
    status: list[StatusSectionRow] = Field(default_factory=list)
    check: list[CheckSectionRow] = Field(default_factory=list)


class FPVR1Report(BaseModel):
    """Typed Application Bundle payload."""

    code: ReportCode = ReportCode.FPVR_1
    title: str = REPORT_TITLES[ReportCode.FPVR_1]
    subject: IdentitySectionRow
    data: FPVR1ReportData


class FPVR1RequestAccepted(BaseModel):
    """FPVR-1 request envelope. ``report`` is set when status is ready."""

    request_id: str
    status: RequestStatusValue
    requested_at: str
    requested_by: str | None = None
    resolution_method: str
    source: RequestSource = RequestSource.external
    report: FPVR1Report | None = None


class FPVR1RequestListResponse(BaseModel):
    """Result set for GET /requests/fpvr-1. ``report`` is not assembled."""

    items: list[FPVR1RequestAccepted]
    total: int
