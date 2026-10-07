"""Official FPVR request workflow: resolve, log, poll, respond."""

from __future__ import annotations

from uuid import uuid4

from app.core.candidates import CandidateTokenError, sign_candidate_id, ssn_from_candidate_id
from app.core.config import get_settings
from app.models.fpvr import (
    AmbiguousSubjectResponse,
    FPVRReportResponse,
    FPVRRequestAccepted,
    FPVRRequestCreate,
    FPVRRequestStatus,
    RequestStatusValue,
    SubjectCandidate,
)
from app.models.subject_identity import SubjectIdentity, SubjectIdentitySearch
from app.services.reports import ReportQueryError, get_report_assembler
from app.services.request_log import RequestLogError, get_request_log_service, utc_now_iso
from app.services.subject_identity import SubjectIdentityQueryError, get_subject_identity_service


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


class RequestNotReadyError(RuntimeError):
    """Raised when the response is fetched before status is ready."""


class FPVRRequestService:
    """Coordinate entity resolution, App SP logging, and OBO report reads."""

    def create(
        self,
        body: FPVRRequestCreate,
        *,
        user_token: str,
        requested_by: str | None,
    ) -> FPVRRequestAccepted:
        """Resolve the subject and log an official request if unique.

        Args:
            body: Report code plus identity filters or candidate_id.
            user_token: Caller token for OBO identity and report SQL.
            requested_by: Caller identity stored on the log row.

        Returns:
            Accepted request with request_id and status.

        Raises:
            CandidateTokenError: Invalid candidate_id.
            SubjectNotFoundError: No matching identity.
            AmbiguousSubjectError: Multiple matches; no request_id issued.
            SubjectIdentityQueryError: Identity SQL failed.
            ReportQueryError: Report SQL failed.
            RequestLogError: App SP log write failed.
        """
        subject, method = self._resolve(body, user_token=user_token)
        status, _payload = get_report_assembler().assemble(
            body.report_code, subject, user_token=user_token
        )
        now = utc_now_iso()
        request_id = str(uuid4())
        dob = None
        if subject.DATE_OF_BIRTH is not None:
            dob = subject.DATE_OF_BIRTH.date().isoformat()
        get_request_log_service().insert(
            request_id=request_id,
            report_code=body.report_code,
            subject_ssn=subject.SSN,
            first_name=subject.FIRST_NAME,
            last_name=subject.LAST_NAME,
            date_of_birth=dob,
            status=status,
            requested_by=requested_by,
            requested_at=now,
            ready_at=now if status == RequestStatusValue.ready else None,
            resolution_method=method,
        )
        return FPVRRequestAccepted(
            request_id=request_id,
            report_code=body.report_code,
            report_title=get_settings().report_title(body.report_code),
            status=status,
            requested_at=now,
            requested_by=requested_by,
            resolution_method=method,
        )

    def status(self, request_id: str, *, user_token: str) -> FPVRRequestStatus:
        """Return request status, re-checking the lake if still pending.

        Args:
            request_id: Public handle.
            user_token: Caller OBO token used when flipping pending to ready.

        Returns:
            Current status (SSN is not included).

        Raises:
            OfficialRequestNotFoundError: Unknown id.
            RequestLogError: Log read/update failed.
            ReportQueryError: Recheck SQL failed.
            SubjectIdentityQueryError: Identity reload failed.
        """
        row = get_request_log_service().get(request_id)
        if row is None:
            raise OfficialRequestNotFoundError(request_id)
        current = RequestStatusValue(row["status"])
        report_code = row["report_code"]
        if report_code not in get_settings().reports:
            raise OfficialRequestNotFoundError(request_id)
        if current == RequestStatusValue.pending:
            subject = self._identity_by_ssn(row["subject_ssn"], user_token=user_token)
            new_status, _ = get_report_assembler().assemble(
                report_code, subject, user_token=user_token
            )
            if new_status == RequestStatusValue.ready:
                ready_at = utc_now_iso()
                get_request_log_service().update_status(
                    request_id, new_status, ready_at=ready_at
                )
                row["status"] = new_status.value
                row["ready_at"] = ready_at
                current = new_status
        return FPVRRequestStatus(
            request_id=row["request_id"],
            report_code=report_code,
            report_title=get_settings().report_title(report_code),
            status=current,
            requested_at=row["requested_at"],
            ready_at=row["ready_at"] or None,
            requested_by=row["requested_by"] or None,
        )

    def response(self, request_id: str, *, user_token: str) -> FPVRReportResponse:
        """Return the report payload if the request is ready.

        Args:
            request_id: Public handle.
            user_token: Caller OBO token for ABAC/RBAC-filtered reads.

        Returns:
            Report JSON without SSN.

        Raises:
            OfficialRequestNotFoundError: Unknown id.
            RequestNotReadyError: Status is not ready.
            ReportQueryError: OBO SQL failed.
            SubjectIdentityQueryError: Identity reload failed.
        """
        snapshot = self.status(request_id, user_token=user_token)
        if snapshot.status != RequestStatusValue.ready:
            raise RequestNotReadyError(request_id)
        row = get_request_log_service().get(request_id)
        if row is None:
            raise OfficialRequestNotFoundError(request_id)
        subject = self._identity_by_ssn(row["subject_ssn"], user_token=user_token)
        _status, payload = get_report_assembler().assemble(
            snapshot.report_code, subject, user_token=user_token
        )
        return FPVRReportResponse(
            request_id=request_id,
            report_code=snapshot.report_code,
            report_title=snapshot.report_title,
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
                    candidate_id=sign_candidate_id(item.SSN),
                    FIRST_NAME=item.FIRST_NAME,
                    LAST_NAME=item.LAST_NAME,
                    DATE_OF_BIRTH=item.DATE_OF_BIRTH,
                    PLACE_OF_BIRTH=item.PLACE_OF_BIRTH,
                    SEX=item.SEX,
                    CITIZENSHIP=item.CITIZENSHIP,
                    MARITAL_STATUS=item.MARITAL_STATUS,
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
