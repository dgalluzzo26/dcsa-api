"""Official FPVR request workflow: resolve, log, poll, respond."""

from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from app.core.candidates import CandidateTokenError, sign_candidate_id, ssn_from_candidate_id
from app.core.config import RequestStatusValue, get_settings
from app.core.jobs import JobKickoffError, run_job_now
from app.models.fpvr import (
    AmbiguousSubjectResponse,
    FPVRReportResponse,
    FPVRRequestAccepted,
    FPVRRequestCreate,
    RequestSource,
    SubjectCandidate,
)
from app.models.subject_identity import SubjectIdentity, SubjectIdentitySearch
from app.services.reports import ReportQueryError, get_report_assembler
from app.services.request_log import RequestLogError, get_request_log_service, utc_now_iso
from app.services.subject_identity import SubjectIdentityQueryError, get_subject_identity_service


def _identity_field(subject: SubjectIdentity, field: str):
    """Read a canonical identity field from a generated row model."""
    return get_settings().identity_value(subject, field)


def _date_of_birth_iso(value) -> str | None:
    """Normalize a generated date-of-birth value to an ISO calendar date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10] if text else None


class SubjectNotFoundError(LookupError):
    """Raised when identity filters match no row."""


class AmbiguousSubjectError(Exception):
    """Raised when identity filters match more than one person.

    Attributes:
        response: Candidate list without SSN.
    """

    def __init__(self, response: AmbiguousSubjectResponse) -> None:
        """Store the 409 body.

        Args:
            response: Ambiguous-match payload.
        """
        super().__init__(response.detail)
        self.response = response


class OfficialRequestNotFoundError(LookupError):
    """Raised when request_id is unknown."""


class FPVRRequestService:
    """Coordinate entity resolution, App SP logging, and OBO report reads."""

    def create(
        self,
        body: FPVRRequestCreate,
        *,
        report_code: str,
        user_token: str,
        requested_by: str | None,
    ) -> FPVRRequestAccepted:
        """Resolve the subject and log an official request if unique.

        Args:
            body: Identity filters or candidate_id.
            report_code: Report implied by the request path.
            user_token: Caller token for OBO identity and report SQL.
            requested_by: Caller identity stored on the log row.

        Returns:
            Accepted request with request_id, status, and report when ready.

        Raises:
            CandidateTokenError: Invalid candidate_id.
            SubjectNotFoundError: No matching identity.
            AmbiguousSubjectError: Multiple matches; no request_id issued.
            SubjectIdentityQueryError: Identity SQL failed.
            ReportQueryError: Report SQL failed or pending job kickoff failed.
            RequestLogError: App SP log write failed.
        """
        subject, method = self._resolve(body, user_token=user_token)
        status, payload = get_report_assembler().assemble(
            report_code, subject, user_token=user_token
        )
        now = utc_now_iso()
        request_id = str(uuid4())
        dob = _date_of_birth_iso(_identity_field(subject, "date_of_birth"))
        subject_ssn = str(_identity_field(subject, "ssn") or "")
        first_name = _identity_field(subject, "first_name")
        last_name = _identity_field(subject, "last_name")
        log = get_request_log_service()
        log.insert(
            request_id=request_id,
            report_code=report_code,
            subject_ssn=subject_ssn,
            first_name=first_name,
            last_name=last_name,
            date_of_birth=dob,
            status=status,
            requested_by=requested_by,
            requested_at=now,
            ready_at=now if status == RequestStatusValue.ready else None,
            resolution_method=method,
            user_token=user_token,
        )
        if status == RequestStatusValue.pending:
            self._kickoff_pending_job(
                request_id,
                report_code=report_code,
                subject_ssn=subject_ssn,
                subject_first_name=first_name,
                subject_last_name=last_name,
                subject_date_of_birth=dob,
                user_token=user_token,
            )
        report = None
        if status == RequestStatusValue.ready:
            report = self._report(report_code, payload)
        return FPVRRequestAccepted(
            request_id=request_id,
            status=status,
            requested_at=now,
            requested_by=requested_by,
            resolution_method=method,
            report=report,
        )

    def get(self, request_id: str, *, user_token: str) -> FPVRRequestAccepted:
        """Return a request, re-checking the lake if still pending.

        Args:
            request_id: Public handle.
            user_token: Caller OBO token used when flipping pending to ready
                and when assembling a ready report.

        Returns:
            Same body as create. ``report`` is set when status is ready.

        Raises:
            OfficialRequestNotFoundError: Unknown id.
            RequestLogError: Log read/update failed.
            ReportQueryError: Recheck or report SQL failed.
            SubjectIdentityQueryError: Identity reload failed.
        """
        row = get_request_log_service().get(request_id, user_token=user_token)
        if row is None:
            raise OfficialRequestNotFoundError(request_id)
        current = RequestStatusValue(row["status"])
        report_code = row["report_code"]
        payload = None
        if report_code not in get_settings().reports:
            raise OfficialRequestNotFoundError(request_id)
        if current == RequestStatusValue.pending:
            subject = self._identity_by_ssn(row["subject_ssn"], user_token=user_token)
            new_status, assembled = get_report_assembler().assemble(
                report_code, subject, user_token=user_token
            )
            if new_status == RequestStatusValue.ready:
                ready_at = utc_now_iso()
                get_request_log_service().update_status(
                    request_id, new_status, ready_at=ready_at, user_token=user_token
                )
                row["status"] = new_status.value
                current = new_status
                payload = assembled
        elif current == RequestStatusValue.ready:
            subject = self._identity_by_ssn(row["subject_ssn"], user_token=user_token)
            _, payload = get_report_assembler().assemble(
                report_code, subject, user_token=user_token
            )
        report = None
        if current == RequestStatusValue.ready and payload is not None:
            report = self._report(report_code, payload)
        return FPVRRequestAccepted(
            request_id=row["request_id"],
            status=current,
            requested_at=row["requested_at"],
            requested_by=row["requested_by"] or None,
            resolution_method=row["resolution_method"] or "",
            request_source=_source_from_row(row),
            report=report,
        )

    def list(
        self,
        query: FPVRRequestListQuery,
        *,
        report_code: ReportCode,
        user_token: str,
    ) -> FPVRRequestListResponse:
        """Return request log rows matching optional filters for one report.

        List does not assemble nested reports; use GET by id for a ready payload.

        Args:
            query: Optional filters. All empty means the newest rows for the report.
            report_code: Report implied by the route.
            user_token: Caller token used when App SP credentials are unset.

        Returns:
            Matching envelopes with ``report`` unset.

        Raises:
            RequestLogError: Log read failed.
        """
        rows = get_request_log_service().list(
            query, report_code=report_code, user_token=user_token
        )
        items = [
            FPVRRequestAccepted(
                request_id=row["request_id"],
                status=RequestStatusValue(row["status"]),
                requested_at=row["requested_at"],
                requested_by=row["requested_by"] or None,
                resolution_method=row["resolution_method"] or "",
                request_source=_source_from_row(row),
                report=None,
            )
            for row in rows
        ]
        return FPVRRequestListResponse(items=items, total=len(items))

    def _report(
        self,
        report_code: str,
        payload: dict,
    ) -> FPVRReportResponse:
        """Build the nested report object from an assembler payload.

        Args:
            report_code: Report produced.
            payload: Assembler map with ``subject`` and ``sections``.

        Returns:
            Report JSON without SSN.
        """
        return FPVRReportResponse(
            code=report_code,
            title=get_settings().report_title(report_code),
            subject=payload["subject"],
            data=payload["sections"],
        )

    def _resolve(
        self, body: FPVRRequestCreate, *, user_token: str
    ) -> tuple[SubjectIdentity, str]:
        """Resolve a unique subject from the create body.

        Args:
            body: Create request.
            user_token: OBO token.

        Returns:
            Resolved identity and resolution_method.

        Raises:
            CandidateTokenError: Bad candidate_id.
            SubjectNotFoundError: No rows.
            AmbiguousSubjectError: Multiple rows.
        """
        if body.candidate_id:
            ssn = ssn_from_candidate_id(body.candidate_id)
            return self._identity_by_ssn(ssn, user_token=user_token), "candidate_id"

        result = get_subject_identity_service().search(
            SubjectIdentitySearch(
                ssn=body.ssn,
                first_name=body.first_name,
                last_name=body.last_name,
                date_of_birth=body.date_of_birth,
                limit=25,
            ),
            user_token=user_token,
        )
        if result.total == 0:
            raise SubjectNotFoundError("No subject matched the supplied identity")
        if result.total > 1:
            candidates = [
                SubjectCandidate(
                    candidate_id=sign_candidate_id(str(_identity_field(item, "ssn") or "")),
                    first_name=_identity_field(item, "first_name") or "",
                    last_name=_identity_field(item, "last_name") or "",
                    date_of_birth=_identity_field(item, "date_of_birth"),
                    place_of_birth=getattr(item, "place_of_birth", None),
                    sex=getattr(item, "sex", None),
                    citizenship=getattr(item, "citizenship", None),
                    marital_status=getattr(item, "marital_status", None),
                )
                for item in result.items
            ]
            raise AmbiguousSubjectError(
                AmbiguousSubjectResponse(candidates=candidates, total=result.total)
            )
        return result.items[0], "unique_match"

    def _identity_by_ssn(self, ssn: str, *, user_token: str) -> SubjectIdentity:
        """Load one identity row by SSN as the caller.

        Args:
            ssn: Subject SSN.
            user_token: OBO token.

        Returns:
            The identity row.

        Raises:
            SubjectNotFoundError: If the SSN is not visible to the caller.
        """
        result = get_subject_identity_service().search(
            SubjectIdentitySearch(ssn=ssn, limit=1),
            user_token=user_token,
        )
        if result.total != 1:
            raise SubjectNotFoundError("Subject is not visible to the caller")
        return result.items[0]

    def _kickoff_pending_job(
        self,
        request_id: str,
        *,
        report_code: str,
        subject_ssn: str,
        subject_first_name: str | None,
        subject_last_name: str | None,
        subject_date_of_birth: str | None,
        user_token: str,
    ) -> None:
        """Start the YAML-configured job once, if this report has ``on_pending``.

        Args:
            request_id: Official request handle.
            report_code: Configured report code.
            subject_ssn: Resolved subject SSN.
            subject_first_name: Resolved first name.
            subject_last_name: Resolved last name.
            subject_date_of_birth: Resolved date of birth as ISO date.
            user_token: Caller OBO token used locally when App SP credentials
                are not configured.

        Raises:
            ReportQueryError: If the Jobs API cannot start the job. The log
                row is marked ``failed`` first.
        """
        job = get_settings().pending_job(report_code)
        if job is None:
            return
        log = get_request_log_service()
        try:
            run_id = run_job_now(
                job,
                request_id=request_id,
                report_code=report_code,
                subject_ssn=subject_ssn,
                subject_first_name=subject_first_name,
                subject_last_name=subject_last_name,
                subject_date_of_birth=subject_date_of_birth,
                user_token=user_token,
            )
        except JobKickoffError as exc:
            log.update_status(request_id, RequestStatusValue.failed)
            raise ReportQueryError(str(exc)) from exc
        log.set_job_run_id(request_id, run_id)


def _source_from_row(row: dict[str, str]) -> RequestSource:
    """Read ``source`` from a log row, defaulting to external.

    Args:
        row: Request log column map.

    Returns:
        Parsed source, or external when missing or unknown.
    """
    raw = (row.get("source") or "").strip()
    try:
        return RequestSource(raw) if raw else RequestSource.external
    except ValueError:
        return RequestSource.external


_fpvr_service: FPVRRequestService | None = None


def get_fpvr_request_service() -> FPVRRequestService:
    """Return the process-wide FPVR request service.

    Returns:
        Shared ``FPVRRequestService``.
    """
    global _fpvr_service
    if _fpvr_service is None:
        _fpvr_service = FPVRRequestService()
    return _fpvr_service
