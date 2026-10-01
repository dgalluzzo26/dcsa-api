"""Assemble FPVR report payloads from edladmin tables via OBO SQL."""

from __future__ import annotations

import re
from typing import Any

from app.core.config import get_settings
from app.core.sql import SqlStatementError, WarehouseNotConfiguredError, execute_obo_statement
from app.models.fpvr import REPORT_TITLES, ReportCode, RequestStatusValue
from app.models.subject_identity import SubjectIdentity

_SCHEMA = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")

# Sources used to mimic each FPVR contract view from the five streaming tables.
REPORT_SOURCES: dict[ReportCode, tuple[str, ...]] = {
    ReportCode.FPVR_1: ("identity", "status", "check"),
    ReportCode.FPVR_2: ("check", "activity"),
    ReportCode.FPVR_3: ("status", "check"),
    ReportCode.FPVR_4: ("identity", "status"),
    ReportCode.FPVR_5: ("signal",),
    ReportCode.FPVR_6: ("identity", "status"),
    ReportCode.FPVR_7: ("status",),
}

_TABLES = {
    "identity": "subject_identity",
    "status": "subject_status",
    "check": "subject_check",
    "activity": "subject_activity",
    "signal": "subject_signal",
}

_SELECT = {
    "identity": (
        "SSN, FIRST_NAME, LAST_NAME, DATE_OF_BIRTH, PLACE_OF_BIRTH, SEX, "
        "CITIZENSHIP, MARITAL_STATUS, UPDATED_TS, RECORD_VERSION"
    ),
    "status": (
        "SSN, ORG_CODE, POSITION_TITLE, DUTY_LOCATION, RISK_TIER, "
        "ELIGIBILITY_LEVEL, STATUS_CODE, STATUS_EFFECTIVE_DATE, UPDATED_TS, "
        "RECORD_VERSION"
    ),
    "check": (
        "CHECK_ID, SSN, LOCATION_CODE, CHECK_TYPE, RESULT_CODE, RESULT_SCORE, "
        "CHECKED_TS, LOAD_SEQ"
    ),
    "activity": (
        "ACTIVITY_ID, SSN, LOCATION_CODE, ACTIVITY_TYPE, DETAIL, EVENT_TS, LOAD_SEQ"
    ),
    "signal": (
        "SIGNAL_ID, SSN, LOCATION_CODE, SIGNAL_TYPE, SEVERITY, SIGNAL_TS, LOAD_SEQ"
    ),
}


class ReportQueryError(RuntimeError):
    """Raised when an OBO report query fails."""


class ReportAssembler:
    """Build FPVR JSON from Unity Catalog as the calling user.

    Attributes:
        _schema: Fully qualified ``catalog.schema``.
    """

    def __init__(self, catalog_schema: str) -> None:
        """Initialize the assembler.

        Args:
            catalog_schema: ``catalog.schema`` holding the subject tables.

        Raises:
            ValueError: If ``catalog_schema`` is not two identifier parts.
        """
        if not _SCHEMA.match(catalog_schema):
            raise ValueError(f"Invalid catalog schema: {catalog_schema!r}")
        self._schema = catalog_schema

    def assemble(
        self, report_code: ReportCode, subject: SubjectIdentity, *, user_token: str
    ) -> tuple[RequestStatusValue, dict[str, Any]]:
        """Query the tables for one report and decide readiness.

        Args:
            report_code: FPVR code.
            subject: Resolved identity (includes SSN for joins only).
            user_token: Caller OBO token.

        Returns:
            Tuple of status (ready or pending) and the data map.

        Raises:
            ReportQueryError: If SQL fails.
        """
        data: dict[str, Any] = {}
        for source in REPORT_SOURCES[report_code]:
            rows = self._query(source, subject.SSN, user_token=user_token)
            data[source] = rows

        ready = self._is_ready(report_code, data)
        public_subject = subject.model_dump()
        public_subject.pop("SSN", None)
        payload = {
            "report_code": report_code.value,
            "report_title": REPORT_TITLES[report_code],
            "subject": public_subject,
            "sections": data,
        }
        status = RequestStatusValue.ready if ready else RequestStatusValue.pending
        return status, payload

    def _is_ready(self, report_code: ReportCode, data: dict[str, Any]) -> bool:
        """Return whether the mock report has enough in-lake rows.

        FPVR-5 (alerts) is ready even with zero signals. FPVR-6 (Human Capital)
        and FPVR-4 are ready when identity is present. Check/status-heavy
        reports stay pending until those tables return rows.

        Args:
            report_code: FPVR code.
            data: Section name to row lists.

        Returns:
            True if the response API should serve the payload.
        """
        if report_code in {ReportCode.FPVR_1, ReportCode.FPVR_4, ReportCode.FPVR_6}:
            return True
        if report_code == ReportCode.FPVR_5:
            return True
        if report_code == ReportCode.FPVR_2:
            return bool(data.get("check") or data.get("activity"))
        if report_code in {ReportCode.FPVR_3, ReportCode.FPVR_7}:
            return bool(data.get("status"))
        return False

    def _query(self, source: str, ssn: str, *, user_token: str) -> list[dict[str, Any]]:
        """Select rows for one source table keyed by SSN.

        Args:
            source: Logical source name (identity, status, ...).
            ssn: Subject SSN.
            user_token: OBO token.

        Returns:
            List of column dicts with SSN stripped.

        Raises:
            ReportQueryError: If the statement fails.
        """
        table = f"{self._schema}.{_TABLES[source]}"
        columns = [c.strip() for c in _SELECT[source].split(",")]
        sql = f"SELECT {_SELECT[source]} FROM {table} WHERE SSN = :ssn"
        try:
            rows = execute_obo_statement(sql, {"ssn": ssn}, user_token=user_token)
        except (WarehouseNotConfiguredError, SqlStatementError) as exc:
            raise ReportQueryError(str(exc)) from exc
        out: list[dict[str, Any]] = []
        for row in rows:
            item = {col: row[i] for i, col in enumerate(columns)}
            item.pop("SSN", None)
            out.append(item)
        return out


_assembler: ReportAssembler | None = None


def get_report_assembler() -> ReportAssembler:
    """Return the process-wide report assembler.

    Returns:
        Shared ``ReportAssembler``.
    """
    global _assembler
    if _assembler is None:
        _assembler = ReportAssembler(get_settings().catalog_schema)
    return _assembler
