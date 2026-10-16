"""Public FPVR API catalog and HTML help."""

from __future__ import annotations

import json
from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.models.report_contract import ApiCatalog
from app.services.catalog import build_catalog

router = APIRouter(tags=["catalog"])


@router.get(
    "/v1/catalog",
    response_model=ApiCatalog,
    summary="FPVR API catalog (schemas, scenarios, per-report examples)",
)
def get_catalog() -> ApiCatalog:
    """Return the caller contract for token, request, status, and response APIs.

    Includes HTTP scenarios and the exact ``data`` section fields for each
    configured report.
    \f
    Returns:
        Typed catalog generated from the same report contract the assembler uses.
    """
    return build_catalog()


def help_page() -> HTMLResponse:
    """Render a human-readable catalog page.

    Returns:
        HTML help document.
    """
    return HTMLResponse(_render_help(build_catalog()))


def _render_help(catalog: ApiCatalog) -> str:
    """Render catalog JSON as a simple HTML document.

    Args:
        catalog: Typed catalog.

    Returns:
        HTML string.
    """
    parts: list[str] = [
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>",
        "<title>DCSA FPVR API catalog</title><style>",
        "body{font:14px/1.45 Helvetica,Arial,sans-serif;color:#1a1a1a;",
        "max-width:960px;margin:24px auto;padding:0 16px}",
        "h1{font-size:22px;margin:0 0 8px}h2{margin:28px 0 8px}",
        "h3{margin:16px 0 6px}",
        ".muted{color:#555} table{border-collapse:collapse;width:100%;",
        "font-size:13px;margin:8px 0 16px} th,td{border-bottom:1px solid #e2e2e2;",
        "text-align:left;vertical-align:top;padding:6px 8px 6px 0}",
        "pre{background:#f5f5f5;padding:10px;overflow:auto;font-size:12px}",
        "code{font-family:Menlo,Consolas,monospace}",
        ".pill{border:1px solid #ccc;padding:1px 6px;font-size:12px}",
        "ul{padding-left:18px}</style></head><body>",
        f"<h1>{escape(catalog.title)}</h1>",
        f"<p class='muted'>Version {escape(catalog.version)}. JSON: ",
        "<a href='/api/v1/catalog'><code>/api/v1/catalog</code></a> · ",
        "Swagger: <a href='/docs'>/docs</a></p>",
        "<ul>",
    ]
    for note in catalog.notes:
        parts.append(f"<li>{escape(note)}</li>")
    parts.append("</ul><h2>APIs and scenarios</h2>")
    for api in catalog.apis:
        parts.append(
            f"<h3><span class='pill'>{escape(api.method)}</span> "
            f"<code>{escape(api.path)}</code></h3>"
        )
        parts.append(f"<p>{escape(api.summary)}</p>")
        parts.append(f"<p class='muted'>Auth: {escape(api.auth)}</p>")
        if api.request_body is not None:
            parts.append("<p>Typical request body</p>")
            parts.append(f"<pre>{escape(json.dumps(api.request_body, indent=2))}</pre>")
        parts.append(
            "<table><thead><tr><th>Scenario</th><th>HTTP</th>"
            "<th>Summary</th></tr></thead><tbody>"
        )
        for sc in api.scenarios:
            parts.append(
                f"<tr><td><code>{escape(sc.id)}</code></td>"
                f"<td>{sc.http_status}</td><td>{escape(sc.summary)}</td></tr>"
            )
        parts.append("</tbody></table>")
        for sc in api.scenarios:
            parts.append(f"<p><strong>{escape(sc.id)}</strong> → {sc.http_status}</p>")
            if sc.request is not None:
                parts.append(f"<pre>{escape(json.dumps(sc.request, indent=2))}</pre>")
            parts.append(f"<pre>{escape(json.dumps(sc.response, indent=2))}</pre>")

    parts.append("<h2>Report response schemas</h2>")
    parts.append(
        "<p class='muted'>GET /api/v1/requests/{id}/response envelope: "
        "request_id, report_code, report_title, subject (no SSN), data "
        "(section name → array of rows, no SSN).</p>"
    )
    for report in catalog.reports:
        parts.append(
            f"<h3>{escape(report.report_code)} — {escape(report.title)}</h3>"
        )
        parts.append(f"<p>{escape(report.readiness)}</p>")
        parts.append(
            f"<p class='muted'>Sources: {escape(', '.join(report.sources))} · "
            f"Tables: {escape(', '.join(report.tables))}</p>"
        )
        for section, fields in report.data_fields.items():
            parts.append(f"<p><code>data.{escape(section)}[]</code></p>")
            parts.append(
                "<table><thead><tr><th>Field</th><th>Type</th>"
                "<th>Nullable</th></tr></thead><tbody>"
            )
            for field in fields:
                parts.append(
                    f"<tr><td><code>{escape(field.name)}</code></td>"
                    f"<td>{escape(field.type)}</td>"
                    f"<td>{'yes' if field.nullable else 'no'}</td></tr>"
                )
            parts.append("</tbody></table>")
        parts.append("<p>Example response</p>")
        parts.append(
            f"<pre>{escape(json.dumps(report.example_response, indent=2))}</pre>"
        )
    parts.append("</body></html>")
    return "".join(parts)
