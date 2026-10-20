"""In-memory official FPVR request store.

Warehouse persistence is disabled for now so local runs do not depend on the
app service principal or ``api_request_log``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.fpvr import RequestStatusValue


class RequestLogError(RuntimeError):
    """Raised when the request log cannot be written or read."""


class RequestLogService:
    """Keep official request rows in process memory."""

    def __init__(self) -> None:
        """Initialize an empty in-memory log."""
        self._rows: dict[str, dict[str, str]] = {}

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
            user_token: Caller token used when App SP credentials are unset (local).

        Raises:
            RequestLogError: If App SP auth or SQL fails.
        """
        self._ensure_table(user_token=user_token)
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
            "job_run_id": "",
        }
        self._execute(sql, params, user_token=user_token)

    def get(self, request_id: str, *, user_token: str | None = None) -> dict[str, str] | None:
        """Fetch one request log row.

        Args:
            request_id: Public request handle.

        Returns:
            Column map or ``None`` if missing.
        """
        row = self._rows.get(request_id)
        return None if row is None else dict(row)
        self._ensure_table(user_token=user_token)
        sql = (
            f"SELECT request_id, report_code, subject_ssn, first_name, last_name, "
            f"date_of_birth, status, requested_by, requested_at, ready_at, "
            f"resolution_method FROM {self._table} WHERE request_id = :request_id "
            "LIMIT 1"
        )
        rows = self._execute(sql, {"request_id": request_id}, user_token=user_token)
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
        user_token: str | None = None,
    ) -> None:
        """Update request status.

        Args:
            request_id: Public request handle.
            status: New status.
            ready_at: Ready timestamp when transitioning to ready.
        """
        row = self._rows.get(request_id)
        if row is None:
            return
        row["status"] = status.value
        if ready_at:
            row["ready_at"] = ready_at

    def set_job_run_id(self, request_id: str, job_run_id: str) -> None:
        """Record the Databricks run started for a pending request.

        Args:
            request_id: Public request handle.
            job_run_id: Jobs API ``run_id``.
        """
        row = self._rows.get(request_id)
        if row is None:
            return
        row["job_run_id"] = job_run_id
        if ready_at:
            sql = (
                f"UPDATE {self._table} SET status = :status, ready_at = :ready_at "
                "WHERE request_id = :request_id"
            )
            params = {"status": status.value, "ready_at": ready_at, "request_id": request_id}
        else:
            sql = f"UPDATE {self._table} SET status = :status WHERE request_id = :request_id"
            params = {"status": status.value, "request_id": request_id}
        self._execute(sql, params, user_token=user_token)

    def _ensure_table(self, *, user_token: str | None = None) -> None:
        """Create the request log table if it does not exist."""
        if self._ensured:
            return
        self._execute(_CREATE_SQL.format(table=self._table), None, user_token=user_token)
        self._ensured = True

    def _execute(
        self, sql: str, params: dict[str, str] | None, *, user_token: str | None = None
    ) -> list:
        """Run SQL as the app service principal, or the caller when SP creds are unset.

        Args:
            sql: Statement text.
            params: Named parameters.
            user_token: Caller token used when DATABRICKS_CLIENT_ID/SECRET are missing.

        Returns:
            Result rows.

        Raises:
            RequestLogError: On auth or SQL failure.
        """
        try:
            try:
                token = get_app_sp_token()
            except AppPrincipalError:
                if not user_token:
                    raise
                token = user_token
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
        _request_log_service = RequestLogService()
    return _request_log_service


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Returns:
        Timestamp with a ``Z`` suffix.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
