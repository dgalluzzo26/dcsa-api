"""Official FPVR request and report schemas."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import ReportCode


class RequestStatusValue(str, Enum):
    """Lifecycle of an official FPVR request."""

    pending = "pending"
    ready = "ready"
    failed = "failed"


class RequestSource(str, Enum):
    """Origin of an official FPVR request."""

    internal = "internal"
    external = "external"


class FPVRSubjectCreate(BaseModel):
    """Identity body for a path-scoped FPVR request. Report code is implied by the route."""

    model_config = ConfigDict(populate_by_name=True)

    ssn: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    candidate_id: str | None = Field(default=None, examples=["abc.def"])

    @model_validator(mode="before")
    @classmethod
    def normalize_input_keys(cls, value: Any) -> Any:
        """Normalize accepted request-key variants without schema aliases.

        Args:
            value: Raw request body.

        Returns:
            Body with alternate keys copied to canonical snake_case names.
        """
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        aliases = {
            "ssn": ("SSN",),
            "first_name": ("FIRST_NAME", "First_Name"),
            "last_name": ("LAST_NAME", "Last_Name"),
            "date_of_birth": ("DATE_OF_BIRTH", "Date_OF_BIRTH"),
        }
        for canonical, alternatives in aliases.items():
            if canonical not in normalized:
                for alternative in alternatives:
                    if alternative in normalized:
                        normalized[canonical] = normalized[alternative]
                        break
        return normalized

    @model_validator(mode="after")
    def require_identity(self) -> "FPVRSubjectCreate":
        """Require a candidate id or at least one identity field.

        Returns:
            The validated model.

        Raises:
            ValueError: If neither a candidate nor identity fields are present.
        """
        if self.candidate_id:
            return self
        if any((self.ssn, self.first_name, self.last_name, self.date_of_birth)):
            return self
        raise ValueError(
            "Provide candidate_id, ssn, or first_name/last_name/date_of_birth"
        )


class FPVRRequestCreate(BaseModel):
    """Body for opening an official FPVR request.

    Report code is implied by the route. Resolve a subject with SSN, or with
    first name + last name + date of birth (SSN optional). If multiple people
    match, resubmit with ``candidate_id``. Extra keys such as ``report_code``
    are ignored.

    Attributes:
        ssn: Optional Social Security Number.
        first_name: Optional first name.
        last_name: Optional last name.
        date_of_birth: Optional date of birth.
        candidate_id: Opaque id from a previous ambiguous match.
    """

    model_config = ConfigDict(populate_by_name=True)

    ssn: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    candidate_id: str | None = Field(default=None, examples=["abc.def"])

    @model_validator(mode="before")
    @classmethod
    def normalize_input_keys(cls, value: Any) -> Any:
        """Normalize accepted request-key variants without schema aliases.

        Args:
            value: Raw request body.

        Returns:
            Body with alternate keys copied to canonical snake_case names.
        """
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        aliases = {
            "ssn": ("SSN",),
            "first_name": ("FIRST_NAME", "First_Name"),
            "last_name": ("LAST_NAME", "Last_Name"),
            "date_of_birth": ("DATE_OF_BIRTH", "Date_OF_BIRTH"),
        }
        for canonical, alternatives in aliases.items():
            if canonical not in normalized:
                for alternative in alternatives:
                    if alternative in normalized:
                        normalized[canonical] = normalized[alternative]
                        break
        return normalized

    @model_validator(mode="after")
    def require_identity(self) -> "FPVRRequestCreate":
        """Require a candidate id or at least one identity field.

        Returns:
            The validated model.

        Raises:
            ValueError: If neither a candidate nor identity fields are present.
        """
        if self.candidate_id:
            return self
        if any((self.ssn, self.first_name, self.last_name, self.date_of_birth)):
            return self
        raise ValueError(
            "Provide candidate_id, ssn, or first_name/last_name/date_of_birth"
        )


class SubjectCandidate(BaseModel):
    """A possible subject match without SSN.

    Attributes:
        candidate_id: Opaque token to resubmit on POST /requests/fpvr-{n}.
        FIRST_NAME: First name.
        LAST_NAME: Last name.
        DATE_OF_BIRTH: Date of birth.
        PLACE_OF_BIRTH: Place of birth.
        SEX: Recorded sex.
        CITIZENSHIP: Citizenship.
        MARITAL_STATUS: Marital status.
    """

    candidate_id: str
    FIRST_NAME: str
    LAST_NAME: str
    DATE_OF_BIRTH: datetime | None = None
    PLACE_OF_BIRTH: str | None = None
    SEX: str | None = None
    CITIZENSHIP: str | None = None
    MARITAL_STATUS: str | None = None


class AmbiguousSubjectResponse(BaseModel):
    """Returned when identity filters match more than one person.

    Attributes:
        detail: Human-readable explanation.
        candidates: Matches without SSN.
        total: Number of candidates returned.
    """

    detail: str = "Multiple subjects matched; provide more information or candidate_id"
    candidates: list[SubjectCandidate]
    total: int


class FPVRReportResponse(BaseModel):
    """Report payload for a ready request.

    Attributes:
        code: Report produced.
        title: Display name.
        subject: Identity fields excluding SSN.
        data: Report-specific rows assembled from Unity Catalog.
    """

    code: ReportCode
    title: str
    subject: dict[str, Any]
    data: dict[str, Any]


class FPVRRequestAccepted(BaseModel):
    """Response when a unique subject is resolved and an official request is logged.

    Mapped onto typed FPVR-n envelopes for POST /requests/fpvr-{n},
    GET /requests/fpvr-{n}, and GET /requests/fpvr-{n}/{id}. Status lives here;
    there is no separate status route.

    Attributes:
        request_id: Handle used to GET the request.
        status: pending, ready, or failed.
        requested_at: Official request timestamp (UTC ISO).
        requested_by: Caller identity stored on the log row.
        resolution_method: unique_match or candidate_id.
        source: internal or external; defaults to external.
        report: Full report when ``status`` is ready; otherwise ``null``.
    """

    request_id: str
    status: RequestStatusValue
    requested_at: str
    requested_by: str | None = None
    resolution_method: str
    source: RequestSource = RequestSource.external
    report: FPVRReportResponse | None = None


class FPVRRequestListQuery(BaseModel):
    """Optional filters for listing official FPVR requests.

    ``requested_at_after`` and ``requested_at_before`` form a range: after only,
    before only, or between when both are set.

    Attributes:
        status: pending, ready, or failed.
        requested_by: Caller identity stored on the log row.
        requested_at_after: Inclusive lower bound on ``requested_at``.
        requested_at_before: Inclusive upper bound on ``requested_at``.
        resolution_method: unique_match or candidate_id.
        source: internal or external.
        limit: Maximum number of rows to return (1-200).
    """

    status: RequestStatusValue | None = None
    requested_by: str | None = None
    requested_at_after: datetime | None = None
    requested_at_before: datetime | None = None
    resolution_method: str | None = None
    source: RequestSource | None = None
    limit: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def require_ordered_requested_at_range(self) -> "FPVRRequestListQuery":
        """Reject inverted requested_at bounds.

        Returns:
            The validated query.

        Raises:
            ValueError: If after is later than before.
        """
        if (
            self.requested_at_after is not None
            and self.requested_at_before is not None
            and self.requested_at_after > self.requested_at_before
        ):
            raise ValueError("requested_at_after must be less than or equal to requested_at_before")
        return self


class FPVRRequestListResponse(BaseModel):
    """Result set returned by GET /requests/fpvr-{n}.

    Attributes:
        items: Matching request envelopes. ``report`` is not assembled on list.
        total: Number of rows in ``items``.
    """

    items: list[FPVRRequestAccepted]
    total: int

class SubjectCandidate(BaseModel):
    """A possible subject match without SSN.

    Attributes:
        candidate_id: Opaque token to resubmit on POST /requests.
        first_name: First name.
        last_name: Last name.
        date_of_birth: Date of birth.
        place_of_birth: Place of birth.
        sex: Recorded sex.
        citizenship: Citizenship.
        marital_status: Marital status.
    """

    candidate_id: str
    first_name: str
    last_name: str
    date_of_birth: date | datetime | None = None
    place_of_birth: str | None = None
    sex: str | None = None
    citizenship: str | None = None
    marital_status: str | None = None


class AmbiguousSubjectResponse(BaseModel):
    """Returned when identity filters match more than one person.

    Attributes:
        detail: Human-readable explanation.
        candidates: Matches without SSN.
        total: Number of candidates returned.
    """

    detail: str = "Multiple subjects matched; provide more information or candidate_id"
    candidates: list[SubjectCandidate]
    total: int
