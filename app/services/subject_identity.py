"""Subject identity lookups against Unity Catalog via OBO SQL.

The service owns query construction and row mapping. It never authenticates as
the app service principal: every query runs with the calling user's token, so
Unity Catalog grants, row filters and column masks apply per user.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.core.config import get_settings
from app.core.sql import (
    SqlStatementError,
    WarehouseNotConfiguredError,
    execute_obo_statement,
)
from app.models.subject_identity import (
    SubjectIdentity,
    SubjectIdentityListResponse,
    SubjectIdentitySearch,
)

_TABLE_NAME = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+){2}$")

_COLUMNS = (
    "SSN",
    "FIRST_NAME",
    "LAST_NAME",
    "DATE_OF_BIRTH",
    "PLACE_OF_BIRTH",
    "SEX",
    "CITIZENSHIP",
    "MARITAL_STATUS",
    "UPDATED_TS",
    "RECORD_VERSION",
)


class SubjectIdentityQueryError(RuntimeError):
    """Raised when the subject identity query fails on the SQL warehouse."""


class SubjectIdentityService:
    """Read-only access to the subject identity table as the calling user.

    Attributes:
        _table: Fully qualified ``catalog.schema.table`` name to query.
    """

    def __init__(self, table: str) -> None:
        """Initialize the service for a specific table.

        Args:
            table: Fully qualified ``catalog.schema.table`` name. Interpolated
                into SQL, so it must be a plain three-part identifier.

        Raises:
            ValueError: If ``table`` is not a plain three-part identifier.
        """
        if not _TABLE_NAME.match(table):
            raise ValueError(f"Invalid subject identity table name: {table!r}")
        self._table = table

    def search(
        self, query: SubjectIdentitySearch, *, user_token: str
    ) -> SubjectIdentityListResponse:
        """Find subject identities matching all provided filters.

        Args:
            query: Validated search filters and result limit.
            user_token: The caller's Databricks access token used for OBO SQL.

        Returns:
            Matching rows, up to ``query.limit``.

        Raises:
            WarehouseNotConfiguredError: If no SQL warehouse is configured.
            SubjectIdentityQueryError: If connecting or querying fails, including
                permission errors for the calling user.
        """
        where, params = self._build_filters(query)
        sql_text = (
            f"SELECT {', '.join(_COLUMNS)} FROM {self._table} "
            f"WHERE {where} LIMIT {int(query.limit)}"
        )
        try:
            rows = execute_obo_statement(sql_text, params, user_token=user_token)
        except WarehouseNotConfiguredError:
            raise
        except SqlStatementError as exc:
            raise SubjectIdentityQueryError(str(exc)) from exc

        items = [self._to_model(tuple(row)) for row in rows]
        return SubjectIdentityListResponse(items=items, total=len(items))

    @staticmethod
    def _build_filters(query: SubjectIdentitySearch) -> tuple[str, dict[str, str]]:
        """Translate search filters into a parameterized ``WHERE`` clause.

        Args:
            query: Validated search filters.

        Returns:
            A tuple of the ``WHERE`` clause body (conditions joined by ``AND``)
            and the named parameters it references.
        """
        clauses: list[str] = []
        params: dict[str, str] = {}
        ssn = re.sub(r"\D", "", query.ssn or "")
        if ssn:
            clauses.append("SSN = :ssn")
            params["ssn"] = ssn
        if first_name := (query.first_name or "").strip():
            clauses.append("lower(FIRST_NAME) = lower(:first_name)")
            params["first_name"] = first_name
        if last_name := (query.last_name or "").strip():
            clauses.append("lower(LAST_NAME) = lower(:last_name)")
            params["last_name"] = last_name
        if query.date_of_birth:
            clauses.append(
                "CAST(DATE_OF_BIRTH AS DATE) = CAST(:date_of_birth AS DATE)"
            )
            params["date_of_birth"] = query.date_of_birth.isoformat()
        return " AND ".join(clauses), params

    @staticmethod
    def _to_model(row: tuple[Any, ...]) -> SubjectIdentity:
        """Map a result row to the response model.

        Args:
            row: Values in ``_COLUMNS`` order.

        Returns:
            The row as a ``SubjectIdentity``.
        """
        values = dict(zip(_COLUMNS, row))
        dob = values["DATE_OF_BIRTH"]
        if isinstance(dob, date) and not isinstance(dob, datetime):
            values["DATE_OF_BIRTH"] = datetime(dob.year, dob.month, dob.day)
        for key, value in values.items():
            if key != "DATE_OF_BIRTH" and value is not None:
                values[key] = str(value)
        return SubjectIdentity.model_validate(values)


_subject_identity_service: SubjectIdentityService | None = None


def get_subject_identity_service() -> SubjectIdentityService:
    """Return the process-wide subject identity service, creating it on first use.

    Returns:
        The shared ``SubjectIdentityService`` bound to the configured table.

    Raises:
        ValueError: If the configured table name is invalid.
    """
    global _subject_identity_service
    if _subject_identity_service is None:
        _subject_identity_service = SubjectIdentityService(
            get_settings().subject_identity_table
        )
    return _subject_identity_service
