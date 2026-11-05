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

    POST /requests and GET /requests/{id} return this same body. Status lives
    here; there is no separate status route.

    Attributes:
        request_id: Handle used to GET the request.
        status: pending, ready, or failed.
        requested_at: Official request timestamp (UTC ISO).
        requested_by: Caller identity stored on the log row.
        resolution_method: unique_match or candidate_id.
        report: Full report when ``status`` is ready; otherwise ``null``.
    """

    request_id: str
    status: RequestStatusValue
    requested_at: str
    requested_by: str | None = None
    resolution_method: str
    report: FPVRReportResponse | None = None

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
