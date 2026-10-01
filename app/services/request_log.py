"""App SP persistence for official FPVR requests."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.core.app_auth import AppPrincipalError, get_app_sp_token
from app.core.config import get_settings
from app.core.sql import SqlStatementError, WarehouseNotConfiguredError, execute_statement
from app.models.fpvr import RequestStatusValue

_TABLE_NAME = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+){2}$")

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
  resolution_method STRING
)
USING DELTA
"""


class RequestLogError(RuntimeError):
    """Raised when the request log cannot be written or read as the app SP."""


class RequestLogService:
    """Insert and update official request rows as the app service principal.

    Attributes:
        _table: Fully qualified request log table.
        _ensured: Whether CREATE TABLE IF NOT EXISTS has been attempted.
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

        Raises:
            RequestLogError: If App SP auth or SQL fails.
        """
        self._ensure_table()
        sql = (
            f"INSERT INTO {self._table} ("
            "request_id, report_code, subject_ssn, first_name, last_name, "
            "date_of_birth, status, requested_by, requested_at, ready_at, "
            "resolution_method) VALUES ("
            ":request_id, :report_code, :subject_ssn, :first_name, :last_name, "
            ":date_of_birth, :status, :requested_by, :requested_at, :ready_at, "
            ":resolution_method)"
        )
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
        }
        self._execute(sql, params)

    def get(self, request_id: str) -> dict[str, str] | None:
        """Fetch one request log row.

        Args:
            request_id: Public request handle.

        Returns:
            Column map or ``None`` if missing.

        Raises:
            RequestLogError: If App SP auth or SQL fails.
        """
        self._ensure_table()
        sql = (
            f"SELECT request_id, report_code, subject_ssn, first_name, last_name, "
            f"date_of_birth, status, requested_by, requested_at, ready_at, "
            f"resolution_method FROM {self._table} WHERE request_id = :request_id "
            "LIMIT 1"
        )
        rows = self._execute(sql, {"request_id": request_id})
        if not rows:
            return None
        keys = (
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
        )
        return {k: ("" if v is None else str(v)) for k, v in zip(keys, rows[0])}

    def update_status(
        self,
        request_id: str,
        status: RequestStatusValue,
        *,
        ready_at: str | None = None,
    ) -> None:
        """Update request status.

        Args:
            request_id: Public request handle.
            status: New status.
            ready_at: Ready timestamp when transitioning to ready.

        Raises:
            RequestLogError: If App SP auth or SQL fails.
        """
        if ready_at:
            sql = (
                f"UPDATE {self._table} SET status = :status, ready_at = :ready_at "
                "WHERE request_id = :request_id"
            )
            params = {"status": status.value, "ready_at": ready_at, "request_id": request_id}
        else:
            sql = f"UPDATE {self._table} SET status = :status WHERE request_id = :request_id"
            params = {"status": status.value, "request_id": request_id}
        self._execute(sql, params)

    def _ensure_table(self) -> None:
        """Create the request log table if it does not exist."""
        if self._ensured:
            return
        self._execute(_CREATE_SQL.format(table=self._table), None)
        self._ensured = True

    def _execute(self, sql: str, params: dict[str, str] | None) -> list:
        """Run SQL as the app service principal.

        Args:
            sql: Statement text.
            params: Named parameters.

        Returns:
            Result rows.

        Raises:
            RequestLogError: On auth or SQL failure.
        """
        try:
            token = get_app_sp_token()
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
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
