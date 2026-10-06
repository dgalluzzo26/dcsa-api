"""Subject identity request/response schemas.

Schemas for lookups against ``dcsa_catalog.edladmin.subject_identity``. Response
field names intentionally mirror the Unity Catalog column names so the API
contract matches the source table.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


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

    ssn: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices("ssn", "SSN"),
            examples=["976782971"],
        ),
    ] = None
    first_name: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices("first_name", "FIRST_NAME", "First_Name"),
            examples=["Kevin"],
        ),
    ] = None
    last_name: Annotated[
        str | None,
        Field(
            validation_alias=AliasChoices("last_name", "LAST_NAME", "Last_Name"),
            examples=["Jackson"],
        ),
    ] = None
    date_of_birth: Annotated[
        date | None,
        Field(
            validation_alias=AliasChoices(
                "date_of_birth", "DATE_OF_BIRTH", "Date_OF_BIRTH"
            ),
            examples=["1969-02-10"],
        ),
    ] = None
    limit: int = Field(default=50, ge=1, le=200)

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
    """A single row from ``dcsa_catalog.edladmin.subject_identity``.

    Attributes:
        SSN: Social Security Number.
        FIRST_NAME: Subject's first name.
        LAST_NAME: Subject's last name.
        DATE_OF_BIRTH: Subject's date of birth.
        PLACE_OF_BIRTH: Subject's place of birth.
        SEX: Subject's recorded sex.
        CITIZENSHIP: Subject's citizenship.
        MARITAL_STATUS: Subject's marital status.
        UPDATED_TS: Timestamp of the last update to the row.
        RECORD_VERSION: Version number of the row.
    """

    SSN: str
    FIRST_NAME: str
    LAST_NAME: str
    DATE_OF_BIRTH: datetime | None = None
    PLACE_OF_BIRTH: str | None = None
    SEX: str | None = None
    CITIZENSHIP: str | None = None
    MARITAL_STATUS: str | None = None
    UPDATED_TS: str | None = None
    RECORD_VERSION: str | None = None


class SubjectIdentityListResponse(BaseModel):
    """Result set returned by a subject identity search.

    Attributes:
        items: Matching subject identity rows.
        total: Number of rows in ``items``.
    """

    items: list[SubjectIdentity]
    total: int
