"""Subject identity request/response schemas.

Response field names are API DTOs from ``mapping.yml``, not Unity Catalog
column names.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SubjectIdentitySearch(BaseModel):
    """Filters for a subject identity lookup.

    All filters are optional individually, but at least one identity field must
    be provided. Provided filters are combined with ``AND``. Input keys accept
    snake_case or the table's column casing (for example ``ssn`` or ``SSN``).

    Attributes:
        ssn: Social Security Number. Non-digit characters are ignored.
        first_name: First name, matched case-insensitively.
        last_name: Last name, matched case-insensitively.
        date_of_birth: Date of birth, matched on the calendar date.
        limit: Maximum number of rows to return (1-200).
    """

    model_config = ConfigDict(populate_by_name=True)

    ssn: str | None = Field(default=None, examples=["976782971"])
    first_name: str | None = Field(default=None, examples=["Kevin"])
    last_name: str | None = Field(default=None, examples=["Jackson"])
    date_of_birth: date | None = Field(default=None, examples=["1969-02-10"])
    limit: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="before")
    @classmethod
    def normalize_input_keys(cls, value: Any) -> Any:
        """Normalize accepted request-key variants without schema aliases.

        Args:
            value: Raw search body.

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
    def require_one_filter(self) -> "SubjectIdentitySearch":
        """Ensure the search is constrained by at least one identity field.

        Returns:
            The validated search model.

        Raises:
            ValueError: If none of ``ssn``, ``first_name``, ``last_name`` or
                ``date_of_birth`` is provided.
        """
        if not any((self.ssn, self.first_name, self.last_name, self.date_of_birth)):
            raise ValueError(
                "Provide at least one of ssn, first_name, last_name, date_of_birth"
            )
        return self


class SubjectIdentity(BaseModel):
    """A single identity row, including ssn for internal joins.

    Attributes:
        ssn: Social Security Number. Returned on identity search only.
        first_name: Subject's first name.
        last_name: Subject's last name.
        date_of_birth: Subject's date of birth.
        place_of_birth: Subject's place of birth.
        sex: Subject's recorded sex.
        citizenship: Subject's citizenship.
        marital_status: Subject's marital status.
        updated_ts: Timestamp of the last update to the row.
        record_version: Version number of the row.
    """

    ssn: str
    first_name: str
    last_name: str
    date_of_birth: datetime | None = None
    place_of_birth: str | None = None
    sex: str | None = None
    citizenship: str | None = None
    marital_status: str | None = None
    updated_ts: str | None = None
    record_version: str | None = None


class SubjectIdentityListResponse(BaseModel):
    """Result set returned by a subject identity search.

    Attributes:
        items: Matching subject identity rows.
        total: Number of rows in ``items``.
    """

    items: list[SubjectIdentity]
    total: int
