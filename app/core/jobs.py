"""Start Databricks jobs as the app service principal."""

from __future__ import annotations

from typing import Any

from app.core.app_auth import AppPrincipalError, get_app_sp_token
from app.core.config import JobConfig, substitute_job_parameters
from app.core.sql import SqlStatementError, _request_json, workspace_host


class JobKickoffError(RuntimeError):
    """Raised when the Jobs API cannot start a configured job."""


def run_job_now(
    job: JobConfig,
    *,
    request_id: str,
    report_code: str,
    subject_ssn: str,
    subject_first_name: str | None = None,
    subject_last_name: str | None = None,
    subject_date_of_birth: str | None = None,
    user_token: str | None = None,
) -> str:
    """Start a Databricks job without waiting for it to finish.

    Args:
        job: YAML job configuration.
        request_id: Official request handle used as the idempotency token.
        report_code: Configured report code.
        subject_ssn: Resolved subject SSN.
        subject_first_name: Resolved first name.
        subject_last_name: Resolved last name.
        subject_date_of_birth: Resolved date of birth as ISO date.
        user_token: Caller OBO token used locally when App SP credentials
            are not configured.

    Returns:
        Databricks ``run_id`` as a string.

    Raises:
        JobKickoffError: If authentication or ``jobs/run-now`` fails.
    """
    parameters = substitute_job_parameters(
        job.parameters,
        request_id=request_id,
        report_code=report_code,
        subject_ssn=subject_ssn,
        subject_first_name=subject_first_name,
        subject_last_name=subject_last_name,
        subject_date_of_birth=subject_date_of_birth,
    )
    payload: dict[str, Any] = {
        "job_id": job.job_id,
        "idempotency_token": request_id,
    }
    if parameters:
        payload["job_parameters"] = parameters
    try:
        access_token = get_app_sp_token(fallback_token=user_token)
        response = _request_json(
            f"{workspace_host()}/api/2.1/jobs/run-now",
            access_token=access_token,
            method="POST",
            payload=payload,
        )
    except (AppPrincipalError, SqlStatementError) as exc:
        raise JobKickoffError(str(exc)) from exc
    run_id = response.get("run_id")
    if run_id is None:
        raise JobKickoffError("Jobs run-now response did not include run_id")
    return str(run_id)
