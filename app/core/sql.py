"""SQL warehouse queries that always run as the calling user (OBO)."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.core.config import SourceColumn, get_settings


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
    """Execute SQL as the calling user (OBO).

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
    return execute_statement(statement, parameters, access_token=user_token)


def execute_statement(
    statement: str,
    parameters: dict[str, str] | None = None,
    *,
    access_token: str,
) -> list[list[Any]]:
    """Execute SQL through the Statement Execution API.

    Unity Catalog grants, row filters and column masks are evaluated for
    ``access_token``. Pass the caller token for OBO reads or the app service
    principal token for request-log writes.

    Args:
        statement: SQL text containing named parameter markers (for example
            ``:ssn``).
        parameters: Named string parameter values.
        access_token: Databricks access token used for the statement.

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
    host = workspace_host()

    payload: dict[str, Any] = {
        "warehouse_id": warehouse_id,
        "statement": statement,
        "wait_timeout": "30s",
        "on_wait_timeout": "CONTINUE",
        "format": "JSON_ARRAY",
        "disposition": "INLINE",
    }
    if parameters:
        payload["parameters"] = [
            {"name": name, "value": value, "type": "STRING"}
            for name, value in parameters.items()
        ]
    response = _request_json(
        f"{host}/api/2.0/sql/statements",
        access_token=access_token,
        method="POST",
        payload=payload,
    )
    statement_id = response.get("statement_id")
    for _ in range(60):
        state = response.get("status", {}).get("state")
        if state == "SUCCEEDED":
            return _collect_rows(host, response, access_token=access_token)
        if state in {"FAILED", "CANCELED", "CLOSED"}:
            error = response.get("status", {}).get("error", {})
            raise SqlStatementError(error.get("message") or f"Statement ended in {state}")
        if not statement_id:
            raise SqlStatementError("Statement API response did not include statement_id")
        time.sleep(1)
        response = _request_json(
            f"{host}/api/2.0/sql/statements/{statement_id}",
            access_token=access_token,
        )
    raise SqlStatementError("SQL statement did not finish within 60 seconds")


def describe_unity_catalog_table(
    full_name: str, *, access_token: str, host: str
) -> list[SourceColumn]:
    """Return Unity Catalog columns for one table or view.

    Args:
        full_name: ``catalog.schema.table`` identifier.
        access_token: Databricks access token.
        host: Workspace base URL.

    Returns:
        Columns in Unity Catalog position order.

    Raises:
        SqlStatementError: If the tables API rejects the request or the
            response has no columns.
    """
    encoded = quote(full_name, safe=".")
    payload = _request_json(
        f"{host.rstrip('/')}/api/2.1/unity-catalog/tables/{encoded}",
        access_token=access_token,
    )
    raw_columns = payload.get("columns") or []
    if not raw_columns:
        raise SqlStatementError(f"Unity Catalog table {full_name!r} has no columns")
    columns: list[SourceColumn] = []
    for index, raw in enumerate(raw_columns):
        name = str(raw.get("name") or "").strip()
        if not name:
            raise SqlStatementError(
                f"Unity Catalog table {full_name!r} has a column with no name"
            )
        type_name = str(raw.get("type_name") or raw.get("type_text") or "STRING")
        position = raw.get("position")
        columns.append(
            SourceColumn(
                name=name,
                type_name=type_name,
                nullable=bool(raw.get("nullable", True)),
                position=int(position) if position is not None else index,
            )
        )
    columns.sort(key=lambda column: column.position)
    return columns


def workspace_host() -> str:
    """Return the Databricks workspace host from settings.

    ``DATABRICKS_HOST`` overrides ``databricks.host`` in ``config.yaml``.

    Returns:
        Absolute ``https://`` workspace URL with no trailing slash.

    Raises:
        WarehouseNotConfiguredError: If the host is empty after loading settings.
    """
    host = get_settings().workspace_host.strip().rstrip("/")
    if not host:
        raise WarehouseNotConfiguredError("Databricks workspace host is not set")
    return host


def _collect_rows(host: str, response: dict[str, Any], *, access_token: str) -> list[list[Any]]:
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
        chunk = _request_json(f"{host}{next_link}", access_token=access_token)
        rows.extend(chunk.get("data_array") or [])
        next_link = chunk.get("next_chunk_internal_link")
    return rows


def _request_json(
    url: str,
    *,
    access_token: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send an authenticated JSON request to a Databricks workspace API.

    Args:
        url: Absolute workspace API URL.
        access_token: Databricks access token.
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
            "Authorization": f"Bearer {access_token}",
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
