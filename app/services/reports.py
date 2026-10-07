"""Assemble report payloads from YAML-configured tables or views via OBO SQL."""

from __future__ import annotations

from typing import Any

from app.core.config import ReportConfig, get_settings
from app.core.sql import SqlStatementError, WarehouseNotConfiguredError, execute_obo_statement
from app.models.fpvr import RequestStatusValue
from app.models.subject_identity import SubjectIdentity


class ReportQueryError(RuntimeError):
    """Raised when an OBO report query fails."""


class ReportAssembler:
    """Build report JSON from configured Unity Catalog tables or views."""

    def __init__(self) -> None:
        """Initialize the assembler from process settings."""
        self._settings = get_settings()

    def assemble(
        self, report_code: str, subject: SubjectIdentity, *, user_token: str
    ) -> tuple[RequestStatusValue, dict[str, Any]]:
        """Query the tables for one report and decide readiness.

        Args:
            report_code: Configured report code.
            subject: Resolved identity (includes SSN for joins only).
            user_token: Caller OBO token.

        Returns:
            Tuple of status (ready or pending) and the data map.

        Raises:
            KeyError: If ``report_code`` is not configured.
            ReportQueryError: If SQL fails.
        """
        report = self._settings.reports[report_code]
        data: dict[str, Any] = {}
        for section_name, section in report.sections.items():
            data[section_name] = self._query(section.source, subject.SSN, user_token=user_token)
            

        ready = self._is_ready(report, data)
        public_subject = subject.model_dump()
        public_subject.pop("SSN", None)
        payload = {
            "report_code": report_code,
            "report_title": report.name,
            "subject": public_subject,
            "sections": data,
        }
        status = RequestStatusValue.ready if ready else RequestStatusValue.pending
        return status, payload

    def _is_ready(self, report: ReportConfig, data: dict[str, Any]) -> bool:
        """Return whether YAML readiness is satisfied.

        Args:
            report: Configured report.
            data: Section name to public row lists.

        Returns:
            True if the response API should serve the payload.
        """
        readiness = report.readiness
        if readiness.mode == "always":
            return True
        if readiness.mode == "section_non_empty":
            return bool(data.get(readiness.section))
        if readiness.mode == "any_section_non_empty":
            return any(data.get(name) for name in (readiness.sections or []))
        for row in data.get(readiness.section) or []:
            value = row.get(readiness.field)
            if value is not None and value != "":
                return True
        return False

    def _query(self, source_name: str, ssn: str, *, user_token: str) -> list[dict[str, Any]]:
        """Select rows for one configured source keyed by the subject filter.

        Args:
            source_name: YAML source key.
            ssn: Subject SSN bound as ``subject_ssn``.
            user_token: OBO token.

        Returns:
            List of column dicts with omitted fields stripped.

        Raises:
            ReportQueryError: If the statement fails.
        """
        source = self._settings.sources[source_name]
        table = self._settings.source_table(source_name)
        columns = list(source.columns)
        sql = (
            f"SELECT {', '.join(columns)} FROM {table} "
            f"WHERE {source.filter.column} = :{source.filter.parameter}"
        )
        try:
            rows = execute_obo_statement(
                sql, {source.filter.parameter: ssn}, user_token=user_token
            )
        except (WarehouseNotConfiguredError, SqlStatementError) as exc:
            raise ReportQueryError(str(exc)) from exc
        omit = set(source.omit_from_output)
        out: list[dict[str, Any]] = []
        for row in rows:
            item = {col: row[i] for i, col in enumerate(columns) if col not in omit}
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
        _assembler = ReportAssembler()
    return _assembler
