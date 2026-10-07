"""Request correlation ids and error logging for Databricks Apps logs."""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger("dcsa")


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Set ``record.request_id`` from the context var.

        Args:
            record: Log record being emitted.

        Returns:
            Always ``True`` so the record is emitted.
        """
        record.request_id = _request_id.get("-")
        return True


def configure_logging() -> None:
    """Configure process logging so request ids appear in Apps logs.

    Adds a ``request_id`` filter to existing handlers (uvicorn already installs
    a stream handler). Does not log SSNs.
    """
    log_filter = RequestIdFilter()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] request_id=%(request_id)s %(message)s"
            )
        )
        root.addHandler(handler)
    for handler in root.handlers:
        handler.addFilter(log_filter)
        fmt = handler.formatter
        if fmt is None or "request_id" not in (getattr(fmt, "_fmt", None) or ""):
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s [%(name)s] request_id=%(request_id)s %(message)s"
                )
            )
    logger.setLevel(logging.INFO)


def current_request_id(request: Request | None = None) -> str:
    """Return the correlation id for this request.

    Args:
        request: Incoming request, if available.

    Returns:
        Request id from state, context, or ``-``.
    """
    if request is not None:
        rid = getattr(request.state, "request_id", None)
        if rid:
            return str(rid)
    return _request_id.get("-")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign ``X-Request-Id`` and log uncaught exceptions."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Bind a request id, invoke the app, and echo the id on the response.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route.

        Returns:
            Downstream response with ``X-Request-Id`` set.
        """
        rid = (request.headers.get("x-request-id") or "").strip() or str(uuid.uuid4())
        request.state.request_id = rid
        token = _request_id.set(rid)
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("%s %s unhandled error", request.method, request.url.path)
            raise
        finally:
            _request_id.reset(token)
        response.headers["X-Request-Id"] = rid
        return response


def log_failure(
    request: Request,
    exc: BaseException,
    *,
    step: str,
    **fields: str | None,
) -> None:
    """Log a caught failure with traceback. Does not log SSN.

    Args:
        request: Incoming request.
        exc: Caught exception.
        step: Stable step name (identity_sql, report_sql, request_log, warehouse).
        **fields: Extra safe fields such as report_code or request_id handle.
    """
    extras = " ".join(f"{key}={value}" for key, value in fields.items() if value)
    logger.exception(
        "%s %s failed step=%s %s error=%s",
        request.method,
        request.url.path,
        step,
        extras,
        exc,
    )


def gateway_error(
    request: Request,
    exc: BaseException,
    *,
    detail: str,
    step: str,
    **fields: str | None,
) -> HTTPException:
    """Log ``exc`` and return a 502 that still hides SSN from the client.

    Args:
        request: Incoming request.
        exc: Caught exception.
        detail: Public error message.
        step: Failure step name for logs.
        **fields: Extra safe log fields.

    Returns:
        HTTPException with 502 and ``X-Request-Id``.
    """
    log_failure(request, exc, step=step, **fields)
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=detail,
        headers={"X-Request-Id": current_request_id(request)},
    )
