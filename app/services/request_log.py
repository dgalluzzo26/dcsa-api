"""App SP (or local token) persistence for official FPVR requests."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.core.app_auth import AppPrincipalError, get_app_sp_token
from app.core.config import get_settings
from app.core.sql import SqlStatementError, WarehouseNotConfiguredError, execute_statement
from app.models.fpvr import FPVRRequestListQuery, ReportCode, RequestSource, RequestStatusValue

_TABLE_NAME = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+){2}$")

_COLUMNS = (
    "request_id",
    "report_code",
    "subject_ssn",
    "first_name",
    "last_name",
    "date_of_birth",
    "status",
    "requested_by",
    "requested_at",
    "ready_at",
    "resolution_method",
    "source",
    "job_run_id",
)

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS {table} (
  request_id STRING,
  report_code STRING,
  subject_ssn STRING,
  first_name STRING,
  last_name STRING,
  date_of_birth STRING,
  status STRING,
  requested_by STRING,
  requested_at STRING,
  ready_at STRING,
  resolution_method STRING,
  source STRING,
  job_run_id STRING
)
USING DELTA
"""

_OPTIONAL_COLUMNS = ("source", "job_run_id")


class RequestLogError(RuntimeError):
    """Raised when the request log cannot be written or read."""


class RequestLogService:
    """Insert, read, and update official request rows in Unity Catalog.

    Locally uses ``DATABRICKS_TOKEN`` (or the caller OBO token) when App SP
    client credentials are unset. On Databricks Apps, uses the app SP token.

    Attributes:
        _table: Fully qualified request log table.
        _ensured: Whether CREATE / ALTER has been attempted.
    """

    def __init__(self, table: str) -> None:
        """Initialize the log service.

        Args:
            table: Fully qualified ``catalog.schema.table`` name.

        Raises:
            ValueError: If ``table`` is not a three-part identifier.
        """
        if not _TABLE_NAME.match(table):
            raise ValueError(f"Invalid request log table name: {table!r}")
        self._table = table
        self._ensured = False

    def insert(
        self,
        *,
        request_id: str,
        report_code: str,
        subject_ssn: str,
        first_name: str | None,
        last_name: str | None,
        date_of_birth: str | None,
        status: RequestStatusValue,
        requested_by: str | None,
        requested_at: str,
        ready_at: str | None,
        resolution_method: str,
        source: RequestSource = RequestSource.external,
        user_token: str | None = None,
    ) -> None:
        """Insert a new official request.

        Args:
            request_id: Public request handle.
            report_code: FPVR report code.
            subject_ssn: Internal join key; never returned to callers on status.
            first_name: Resolved first name.
            last_name: Resolved last name.
            date_of_birth: Resolved date of birth as ISO date.
            status: Initial status.
            requested_by: Caller identity.
            requested_at: UTC timestamp string.
            ready_at: UTC timestamp if already ready.
            resolution_method: unique_match or candidate_id.
            source: internal or external; defaults to external.
            user_token: Caller token used when App SP credentials are unset.

        Raises:
            RequestLogError: If auth or SQL fails.
        """
        self._ensure_table(user_token=user_token)
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join(f":{name}" for name in _COLUMNS)
        sql = f"INSERT INTO {self._table} ({cols}) VALUES ({placeholders})"
        params = {
            "request_id": request_id,
            "report_code": report_code,
            "subject_ssn": subject_ssn,
            "first_name": first_name or "",
            "last_name": last_name or "",
            "date_of_birth": date_of_birth or "",
            "status": status.value,
            "requested_by": requested_by or "",
            "requested_at": requested_at,
            "ready_at": ready_at or "",
            "resolution_method": resolution_method,
            "source": source.value,
            "job_run_id": "",
        }
        self._execute(sql, params, user_token=user_token)

    def get(self, request_id: str, *, user_token: str | None = None) -> dict[str, str] | None:
        """Fetch one request log row.

        Args:
            request_id: Public request handle.
            user_token: Caller token used when App SP credentials are unset.

        Returns:
            Column map or ``None`` if missing.

        Raises:
            RequestLogError: If auth or SQL fails.
        """
        self._ensure_table(user_token=user_token)
        cols = ", ".join(_COLUMNS)
        sql = (
            f"SELECT {cols} FROM {self._table} "
            "WHERE request_id = :request_id LIMIT 1"
        )
        rows = self._execute(sql, {"request_id": request_id}, user_token=user_token)
        if not rows:
            return None
        return {k: ("" if v is None else str(v)) for k, v in zip(_COLUMNS, rows[0])}

    def list(
        self,
        query: FPVRRequestListQuery,
        *,
        report_code: ReportCode | None = None,
        user_token: str | None = None,
    ) -> list[dict[str, str]]:
        """Return request log rows matching optional filters.

        Args:
            query: Optional status, caller, requested_at range, resolution, source.
            report_code: When set, restrict to that report.
            user_token: Caller token used when App SP credentials are unset.

        Returns:
            Matching column maps, newest ``requested_at`` first.

        Raises:
            RequestLogError: If auth or SQL fails.
        """
        self._ensure_table(user_token=user_token)
        clauses: list[str] = []
        params: dict[str, str] = {}
        if report_code is not None:
            clauses.append("report_code = :report_code")
            params["report_code"] = report_code.value
        if query.status is not None:
            clauses.append("status = :status")
            params["status"] = query.status.value
        if query.requested_by is not None:
            clauses.append("requested_by = :requested_by")
            params["requested_by"] = query.requested_by
        if query.requested_at_after is not None:
            clauses.append("requested_at >= :requested_at_after")
            params["requested_at_after"] = _utc_iso(query.requested_at_after)
        if query.requested_at_before is not None:
            clauses.append("requested_at <= :requested_at_before")
            params["requested_at_before"] = _utc_iso(query.requested_at_before)
        if query.resolution_method is not None:
            clauses.append("resolution_method = :resolution_method")
            params["resolution_method"] = query.resolution_method
        if query.source is not None:
            clauses.append("source = :source")
            params["source"] = query.source.value
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cols = ", ".join(_COLUMNS)
        sql = (
            f"SELECT {cols} FROM {self._table} {where} "
            f"ORDER BY requested_at DESC LIMIT {int(query.limit)}"
        )
        rows = self._execute(sql, params or None, user_token=user_token)
        return [
            {k: ("" if v is None else str(v)) for k, v in zip(_COLUMNS, row)}
            for row in rows
        ]

    def update_status(
        self,
        request_id: str,
        status: RequestStatusValue,
        *,
        ready_at: str | None = None,
        user_token: str | None = None,
    ) -> None:
        """Update request status.

        Args:
            request_id: Public request handle.
            status: New status.
            ready_at: Ready timestamp when transitioning to ready.
            user_token: Caller token used when App SP credentials are unset.

        Raises:
            RequestLogError: If auth or SQL fails.
        """
        self._ensure_table(user_token=user_token)
        if ready_at:
            sql = (
                f"UPDATE {self._table} SET status = :status, ready_at = :ready_at "
                "WHERE request_id = :request_id"
            )
            params = {
                "status": status.value,
                "ready_at": ready_at,
                "request_id": request_id,
            }
        else:
            sql = (
                f"UPDATE {self._table} SET status = :status "
                "WHERE request_id = :request_id"
            )
            params = {"status": status.value, "request_id": request_id}
        self._execute(sql, params, user_token=user_token)

    def set_job_run_id(
        self, request_id: str, job_run_id: str, *, user_token: str | None = None
    ) -> None:
        """Record the Databricks run started for a pending request.

        Args:
            request_id: Public request handle.
            job_run_id: Jobs API ``run_id``.
            user_token: Caller token used when App SP credentials are unset.

        Raises:
            RequestLogError: If auth or SQL fails.
        """
        self._ensure_table(user_token=user_token)
        sql = (
            f"UPDATE {self._table} SET job_run_id = :job_run_id "
            "WHERE request_id = :request_id"
        )
        self._execute(
            sql,
            {"job_run_id": job_run_id, "request_id": request_id},
            user_token=user_token,
        )

    def _ensure_table(self, *, user_token: str | None = None) -> None:
        """Create the request log table and migrate optional columns."""
        if self._ensured:
            return
        self._execute(_CREATE_SQL.format(table=self._table), None, user_token=user_token)
        existing = {
            (row[0] or "").lower()
            for row in self._execute(
                f"DESCRIBE TABLE {self._table}", None, user_token=user_token
            )
            if row and row[0]
        }
        missing = [name for name in _OPTIONAL_COLUMNS if name not in existing]
        if missing:
            added = ", ".join(f"{name} STRING" for name in missing)
            self._execute(
                f"ALTER TABLE {self._table} ADD COLUMNS ({added})",
                None,
                user_token=user_token,
            )
        self._ensured = True

    def _execute(
        self, sql: str, params: dict[str, str] | None, *, user_token: str | None = None
    ) -> list:
        """Run SQL as the app SP, or the caller when SP credentials are unset.

        Args:
            sql: Statement text.
            params: Named parameters.
            user_token: Caller token used when DATABRICKS_CLIENT_ID/SECRET and
                DATABRICKS_TOKEN are missing.

        Returns:
            Result rows.

        Raises:
            RequestLogError: On auth or SQL failure.
        """
        try:
            token = get_app_sp_token(fallback_token=user_token)
            return execute_statement(sql, params, access_token=token)
        except (AppPrincipalError, WarehouseNotConfiguredError, SqlStatementError) as exc:
            raise RequestLogError(str(exc)) from exc


_request_log_service: RequestLogService | None = None


def get_request_log_service() -> RequestLogService:
    """Return the process-wide request log service.

    Returns:
        Shared ``RequestLogService``.
    """
    global _request_log_service
    if _request_log_service is None:
        _request_log_service = RequestLogService(get_settings().request_log_table)
    return _request_log_service


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Returns:
        Timestamp with a ``Z`` suffix.
    """
    return _utc_iso(datetime.now(timezone.utc))


def _utc_iso(value: datetime) -> str:
    """Format a timestamp as UTC ISO-8601 with a ``Z`` suffix.

    Args:
        value: Aware or naive datetime. Naive values are treated as UTC.

    Returns:
        Second-precision UTC timestamp.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
