"""Official FPVR request and report schemas."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RequestStatusValue(str, Enum):
    """Lifecycle of an official FPVR request."""

    pending = "pending"
    ready = "ready"
    failed = "failed"


class FPVRRequestCreate(BaseModel):
    """Body for opening an official FPVR request.

    Resolve a subject with SSN, or with first name + last name + date of birth
    (SSN optional). If multiple people match, resubmit with ``candidate_id``.

    Attributes:
        report_code: Which configured report to produce.
        ssn: Optional Social Security Number.
        first_name: Optional first name.
        last_name: Optional last name.
        date_of_birth: Optional date of birth.
        candidate_id: Opaque id from a previous ambiguous match.
    """

    model_config = ConfigDict(populate_by_name=True)

    report_code: str = Field(min_length=1, examples=["FPVR-6"])
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
            "report_code": ("reportCode", "REPORT_CODE"),
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
    def require_identity_and_report(self) -> "FPVRRequestCreate":
        """Require a known report code plus identity fields or a candidate id.

        Returns:
            The validated model.

        Raises:
            ValueError: If the report is unknown or identity is missing.
        """
        from app.core.config import get_settings

        if self.report_code not in get_settings().reports:
            raise ValueError(f"Unknown report_code: {self.report_code}")
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
        candidate_id: Opaque token to resubmit on POST /requests.
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


class FPVRRequestAccepted(BaseModel):
    """Response when a unique subject is resolved and an official request is logged.

    Attributes:
        request_id: Handle used for status and response calls.
        report_code: Requested report.
        report_title: Display name of the report.
        status: pending, ready, or failed.
        requested_at: Official request timestamp (UTC ISO).
        requested_by: Caller identity stored on the log row.
        resolution_method: unique_match or candidate_id.
    """

    request_id: str
    report_code: str
    report_title: str
    status: RequestStatusValue
    requested_at: str
    requested_by: str | None = None
    resolution_method: str


class FPVRRequestStatus(BaseModel):
    """Status of an official request.

    Attributes:
        request_id: Request handle.
        report_code: Requested report.
        report_title: Display name.
        status: pending, ready, or failed.
        requested_at: When the request was logged.
        ready_at: When the payload became servable, if ready.
        requested_by: Caller identity.
    """

    request_id: str
    report_code: str
    report_title: str
    status: RequestStatusValue
    requested_at: str
    ready_at: str | None = None
    requested_by: str | None = None


class FPVRReportResponse(BaseModel):
    """Report payload for a ready request.

    Attributes:
        request_id: Request handle.
        report_code: Report produced.
        report_title: Display name.
        subject: Identity fields excluding SSN.
        data: Report-specific rows assembled from Unity Catalog.
    """

    request_id: str
    report_code: str
    report_title: str
    subject: dict[str, Any]
    data: dict[str, Any]
