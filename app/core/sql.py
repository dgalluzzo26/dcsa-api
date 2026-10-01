"""SQL warehouse queries that always run as the calling user (OBO)."""

from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings


class WarehouseNotConfiguredError(RuntimeError):
    """Raised when the workspace host or SQL warehouse id is not configured."""


class SqlStatementError(RuntimeError):
    """Raised when the SQL Statement Execution API rejects or fails a query."""


def execute_obo_statement(
    statement: str,
    parameters: dict[str, str],
    *,
    user_token: str,
) -> list[list[Any]]:
    """Execute SQL through the Statement Execution API as the calling user.

    This standard-library implementation avoids a runtime dependency on the
    Databricks SQL connector. Unity Catalog permissions, row filters and column
    masks are evaluated for ``user_token``.

    Args:
        statement: SQL text containing named parameter markers (for example
            ``:ssn``).
        parameters: Named string parameter values.
        user_token: The caller's Databricks access token.

    Returns:
        Result rows in statement column order.

    Raises:
        WarehouseNotConfiguredError: If the host or warehouse id is empty.
        SqlStatementError: If the API request or SQL statement fails.
    """
    settings = get_settings()
    warehouse_id = settings.warehouse_id
    if not warehouse_id:
        raise WarehouseNotConfiguredError("DATABRICKS_WAREHOUSE_ID is not set")
    host = os.getenv("DATABRICKS_HOST", "").rstrip("/")
    if not host:
        raise WarehouseNotConfiguredError("DATABRICKS_HOST is not set")
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"

    payload = {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "parameters": [
            {"name": name, "value": value, "type": "STRING"}
            for name, value in parameters.items()
        ],
        "wait_timeout": "30s",
        "on_wait_timeout": "CONTINUE",
        "format": "JSON_ARRAY",
        "disposition": "INLINE",
    }
    response = _request_json(
        f"{host}/api/2.0/sql/statements",
        user_token=user_token,
        method="POST",
        payload=payload,
    )
    statement_id = response.get("statement_id")
    for _ in range(60):
        state = response.get("status", {}).get("state")
        if state == "SUCCEEDED":
            return _collect_rows(host, response, user_token=user_token)
        if state in {"FAILED", "CANCELED", "CLOSED"}:
            error = response.get("status", {}).get("error", {})
            raise SqlStatementError(error.get("message") or f"Statement ended in {state}")
        if not statement_id:
            raise SqlStatementError("Statement API response did not include statement_id")
        time.sleep(1)
        response = _request_json(
            f"{host}/api/2.0/sql/statements/{statement_id}",
            user_token=user_token,
        )
    raise SqlStatementError("SQL statement did not finish within 60 seconds")


def _collect_rows(host: str, response: dict[str, Any], *, user_token: str) -> list[list[Any]]:
    """Collect the inline result and any additional result chunks.

    Args:
        host: Workspace base URL.
        response: Successful statement response.
        user_token: The caller's Databricks access token.

    Returns:
        All result rows.
    """
    result = response.get("result") or {}
    rows = list(result.get("data_array") or [])
    next_link = result.get("next_chunk_internal_link")
    while next_link:
        chunk = _request_json(f"{host}{next_link}", user_token=user_token)
        rows.extend(chunk.get("data_array") or [])
        next_link = chunk.get("next_chunk_internal_link")
    return rows


def _request_json(
    url: str,
    *,
    user_token: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send an authenticated JSON request to a Databricks workspace API.

    Args:
        url: Absolute workspace API URL.
        user_token: The caller's Databricks access token.
        method: HTTP method.
        payload: Optional JSON request body.

    Returns:
        Decoded JSON response.

    Raises:
        SqlStatementError: If the HTTP request or response decoding fails.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {user_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=40) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SqlStatementError(f"Databricks API returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SqlStatementError(f"Databricks API request failed: {exc}") from exc
