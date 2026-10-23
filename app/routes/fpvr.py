"""Official FPVR request HTTP routes."""
import importlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.candidates import CandidateTokenError
from app.core.config import RequestStatusValue, get_settings
from app.core.http_logging import current_request_id, gateway_error, log_failure
from app.core.obo import bearer_scheme, get_obo_token
from app.core.sql import WarehouseNotConfiguredError
from app.models import ErrorResponse
from app.models.fpvr import (
    AmbiguousSubjectResponse,
    OfficialRequestCreate,
)

from app.services.fpvr import (
    AmbiguousSubjectError,
    FPVRRequestService,
    OfficialRequestNotFoundError,
    SubjectNotFoundError,
    get_fpvr_request_service,
)
from app.services.reports import ReportQueryError
from app.services.request_log import RequestLogError, get_request_log_service
from app.services.subject_identity import SubjectIdentityQueryError

router = APIRouter(
    prefix="/v1/requests",
    tags=["fpvr-requests"],
    dependencies=[Depends(bearer_scheme)],
)

_RETRY_AFTER_SECONDS = "5"

_ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": AmbiguousSubjectResponse},
    422: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _caller(request: Request) -> str | None:
    """Best available caller identifier for the request log.

    Args:
        request: Incoming HTTP request.

    Returns:
        Email, preferred username, user id, or None.
    """
    email = (request.headers.get("x-forwarded-email") or "").strip()
    preferred = (request.headers.get("x-forwarded-preferred-username") or "").strip()
    user = (request.headers.get("x-forwarded-user") or "").strip()
    return email or preferred or user or None


def _service() -> FPVRRequestService:
    """Return the FPVR request service.

    Returns:
        Shared service instance.
    """
    return get_fpvr_request_service()


def _import_report_module(report_code: str):
    try:
        module = importlib.import_module(f"app.models.reports.{report_code.upper()}")
    except ModuleNotFoundError:
        try:
            module = importlib.import_module(f"app.models.reports.{report_code.lower()}")
        except ModuleNotFoundError:
            raise ValueError(f"Unknown report code: {report_code}")
    return module


def _get_ready_reports():
    """Return report module names under ``app.models.reports``.

    The directory is resolved from this file so discovery works no matter
    which working directory the process was started from.
    """
    dir_path = Path(__file__).resolve().parent.parent / "models" / "reports"

    reports = [
        item.stem
        for item in dir_path.iterdir()
        if item.is_file() and item.suffix == ".py" and not item.name.startswith("_")
    ]

    return {
        report_code: getattr(
            _import_report_module(report_code), f"{report_code.upper()}RequestAccepted"
        )
        for report_code in reports
    }


def _register_report_endpoint(report_code: str, response_model):
    report_title = get_settings().report_title(report_code)

    @router.post(
        f"/{report_code}",
        response_model=response_model,
        status_code=201,
        summary=f"Open an official {report_code} {report_title} request",
        responses=_ERROR_RESPONSES,
    )
    def create_report_request(request: Request, body: OfficialRequestCreate, response: Response):
        token = get_obo_token(request)
        try:
            accepted = _service().create(
                body,
                report_code=report_code,
                user_token=token,
                requested_by=_caller(request),
            )
            response.headers["Location"] = f"/api/v1/requests/{report_code}/{accepted.request_id}"
            if accepted.status == RequestStatusValue.pending:
                response.headers["Retry-After"] = _RETRY_AFTER_SECONDS
            return response_model.model_validate(accepted.model_dump())
        except CandidateTokenError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from e
        except SubjectNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
        except AmbiguousSubjectError as e:
            content = e.response.model_dump(mode="json")
            content["request_id"] = current_request_id(request)
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=content,
                headers={"X-Request-Id": current_request_id(request)},
            )
        except WarehouseNotConfiguredError as e:
            log_failure(request, e, step="warehouse", report_code=report_code)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
        except SubjectIdentityQueryError as e:
            raise gateway_error(
                request, e, detail="FPVR request failed", step="identity_sql",
                report_code=report_code,
            ) from e
        except ReportQueryError as e:
            raise gateway_error(
                request, e, detail="FPVR request failed", step="report_sql",
                report_code=report_code,
            ) from e
        except RequestLogError as e:
            raise gateway_error(
                request, e, detail="FPVR request failed", step="request_log",
                report_code=report_code,
            ) from e

    @router.get(
        f"/{report_code}/{{request_id}}",
        response_model=response_model,
        summary=f"Get an official {report_code} {report_title} request",
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            502: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    def get_report_request(request: Request, request_id: str, response: Response):
        """Return the same typed body as the matching POST route.

        Unknown ids or requests logged for another report code return 404.
        \f
        Args:
            request: Incoming request carrying the caller token.
            request_id: Handle from POST /v1/requests/{report_code}.
            response: FastAPI response used to set Retry-After.

        Returns:
            Request envelope. ``report`` is set when ready.

        Raises:
            HTTPException: 401/404/502/503.
        """
        token = get_obo_token(request)
        try:
            row = get_request_log_service().get(request_id, user_token=token)
            if row is None or row.get("report_code") != report_code:
                raise OfficialRequestNotFoundError(request_id)
            accepted = _service().get(request_id, user_token=token)
            if accepted.status == RequestStatusValue.pending:
                response.headers["Retry-After"] = _RETRY_AFTER_SECONDS
            return response_model.model_validate(accepted.model_dump())
        except OfficialRequestNotFoundError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found") from e
        except WarehouseNotConfiguredError as e:
            log_failure(request, e, step="warehouse", fpvr_request_id=request_id)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
        except SubjectIdentityQueryError as e:
            raise gateway_error(
                request, e, detail="Status lookup failed", step="identity_sql",
                fpvr_request_id=request_id,
            ) from e
        except ReportQueryError as e:
            raise gateway_error(
                request, e, detail="Status lookup failed", step="report_sql",
                fpvr_request_id=request_id,
            ) from e
        except RequestLogError as e:
            raise gateway_error(
                request, e, detail="Status lookup failed", step="request_log",
                fpvr_request_id=request_id,
            ) from e


for report_code, response_model in _get_ready_reports().items():
    _register_report_endpoint(report_code, response_model)
