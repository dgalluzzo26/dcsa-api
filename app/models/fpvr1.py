"""Typed request and response models for the FPVR-1 Application Bundle API."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.fpvr import RequestStatusValue, ReportCode, REPORT_TITLES
from app.models.report_contract import CheckSectionRow, IdentitySectionRow, StatusSectionRow


class FPVR1RequestCreate(BaseModel):
    """Body for opening an FPVR-1 request. Report code is implied by the route."""

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
    def require_identity(self) -> "FPVR1RequestCreate":
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
    report: FPVR1Report | None = None
