"""Typed request and response models for FPVR-2 through FPVR-7."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.fpvr import (
    FPVRSubjectCreate,
    REPORT_TITLES,
    ReportCode,
    RequestSource,
    RequestStatusValue,
)
from app.models.report_contract import (
    ActivitySectionRow,
    CheckSectionRow,
    IdentitySectionRow,
    SignalSectionRow,
    StatusSectionRow,
)


class FPVR2RequestCreate(FPVRSubjectCreate):
    """Body for opening an FPVR-2 request. Report code is implied by the route."""


class FPVR2ReportData(BaseModel):
    """FPVR-2 ``data`` sections: check and activity."""

    check: list[CheckSectionRow] = Field(default_factory=list)
    activity: list[ActivitySectionRow] = Field(default_factory=list)


class FPVR2Report(BaseModel):
    """Typed Investigation Summary payload."""

    code: ReportCode = ReportCode.FPVR_2
    title: str = REPORT_TITLES[ReportCode.FPVR_2]
    subject: IdentitySectionRow
    data: FPVR2ReportData


class FPVR2RequestAccepted(BaseModel):
    """FPVR-2 request envelope. ``report`` is set when status is ready."""

    request_id: str
    status: RequestStatusValue
    requested_at: str
    requested_by: str | None = None
    resolution_method: str
    source: RequestSource = RequestSource.external
    report: FPVR2Report | None = None


class FPVR2RequestListResponse(BaseModel):
    """Result set for GET /requests/fpvr-2. ``report`` is not assembled."""

    items: list[FPVR2RequestAccepted]
    total: int


class FPVR3RequestCreate(FPVRSubjectCreate):
    """Body for opening an FPVR-3 request. Report code is implied by the route."""


class FPVR3ReportData(BaseModel):
    """FPVR-3 ``data`` sections: status and check."""

    status: list[StatusSectionRow] = Field(default_factory=list)
    check: list[CheckSectionRow] = Field(default_factory=list)


class FPVR3Report(BaseModel):
    """Typed Adjudication Summary payload."""

    code: ReportCode = ReportCode.FPVR_3
    title: str = REPORT_TITLES[ReportCode.FPVR_3]
    subject: IdentitySectionRow
    data: FPVR3ReportData


class FPVR3RequestAccepted(BaseModel):
    """FPVR-3 request envelope. ``report`` is set when status is ready."""

    request_id: str
    status: RequestStatusValue
    requested_at: str
    requested_by: str | None = None
    resolution_method: str
    source: RequestSource = RequestSource.external
    report: FPVR3Report | None = None


class FPVR3RequestListResponse(BaseModel):
    """Result set for GET /requests/fpvr-3. ``report`` is not assembled."""

    items: list[FPVR3RequestAccepted]
    total: int


class FPVR4RequestCreate(FPVRSubjectCreate):
    """Body for opening an FPVR-4 request. Report code is implied by the route."""


class FPVR4ReportData(BaseModel):
    """FPVR-4 ``data`` sections: identity and status."""

    identity: list[IdentitySectionRow] = Field(default_factory=list)
    status: list[StatusSectionRow] = Field(default_factory=list)


class FPVR4Report(BaseModel):
    """Typed CV Summary payload."""

    code: ReportCode = ReportCode.FPVR_4
    title: str = REPORT_TITLES[ReportCode.FPVR_4]
    subject: IdentitySectionRow
    data: FPVR4ReportData


class FPVR4RequestAccepted(BaseModel):
    """FPVR-4 request envelope. ``report`` is set when status is ready."""

    request_id: str
    status: RequestStatusValue
    requested_at: str
    requested_by: str | None = None
    resolution_method: str
    source: RequestSource = RequestSource.external
    report: FPVR4Report | None = None


class FPVR4RequestListResponse(BaseModel):
    """Result set for GET /requests/fpvr-4. ``report`` is not assembled."""

    items: list[FPVR4RequestAccepted]
    total: int


class FPVR5RequestCreate(FPVRSubjectCreate):
    """Body for opening an FPVR-5 request. Report code is implied by the route."""


class FPVR5ReportData(BaseModel):
    """FPVR-5 ``data`` sections: signal."""

    signal: list[SignalSectionRow] = Field(default_factory=list)


class FPVR5Report(BaseModel):
    """Typed CV Alerts payload."""

    code: ReportCode = ReportCode.FPVR_5
    title: str = REPORT_TITLES[ReportCode.FPVR_5]
    subject: IdentitySectionRow
    data: FPVR5ReportData


class FPVR5RequestAccepted(BaseModel):
    """FPVR-5 request envelope. ``report`` is set when status is ready."""

    request_id: str
    status: RequestStatusValue
    requested_at: str
    requested_by: str | None = None
    resolution_method: str
    source: RequestSource = RequestSource.external
    report: FPVR5Report | None = None


class FPVR5RequestListResponse(BaseModel):
    """Result set for GET /requests/fpvr-5. ``report`` is not assembled."""

    items: list[FPVR5RequestAccepted]
    total: int


class FPVR6RequestCreate(FPVRSubjectCreate):
    """Body for opening an FPVR-6 request. Report code is implied by the route."""


class FPVR6ReportData(BaseModel):
    """FPVR-6 ``data`` sections: identity and status."""

    identity: list[IdentitySectionRow] = Field(default_factory=list)
    status: list[StatusSectionRow] = Field(default_factory=list)


class FPVR6Report(BaseModel):
    """Typed Human Capital payload."""

    code: ReportCode = ReportCode.FPVR_6
    title: str = REPORT_TITLES[ReportCode.FPVR_6]
    subject: IdentitySectionRow
    data: FPVR6ReportData


class FPVR6RequestAccepted(BaseModel):
    """FPVR-6 request envelope. ``report`` is set when status is ready."""

    request_id: str
    status: RequestStatusValue
    requested_at: str
    requested_by: str | None = None
    resolution_method: str
    source: RequestSource = RequestSource.external
    report: FPVR6Report | None = None


class FPVR6RequestListResponse(BaseModel):
    """Result set for GET /requests/fpvr-6. ``report`` is not assembled."""

    items: list[FPVR6RequestAccepted]
    total: int


class FPVR7RequestCreate(FPVRSubjectCreate):
    """Body for opening an FPVR-7 request. Report code is implied by the route."""


class FPVR7ReportData(BaseModel):
    """FPVR-7 ``data`` sections: status."""

    status: list[StatusSectionRow] = Field(default_factory=list)


class FPVR7Report(BaseModel):
    """Typed Favorable to Onboard payload."""

    code: ReportCode = ReportCode.FPVR_7
    title: str = REPORT_TITLES[ReportCode.FPVR_7]
    subject: IdentitySectionRow
    data: FPVR7ReportData


class FPVR7RequestAccepted(BaseModel):
    """FPVR-7 request envelope. ``report`` is set when status is ready."""

    request_id: str
    status: RequestStatusValue
    requested_at: str
    requested_by: str | None = None
    resolution_method: str
    source: RequestSource = RequestSource.external
    report: FPVR7Report | None = None


class FPVR7RequestListResponse(BaseModel):
    """Result set for GET /requests/fpvr-7. ``report`` is not assembled."""

    items: list[FPVR7RequestAccepted]
    total: int
