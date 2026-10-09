"""Build the public FPVR API catalog from the report contract."""

from __future__ import annotations

from typing import Any

from app import __version__
from app.core.config import get_settings
from app.core.sql import WarehouseNotConfiguredError, workspace_host
from app.models.fpvr import ReportCode
from app.models.report_contract import (
    SECTION_ROW_MODELS,
    ApiCatalog,
    CatalogApi,
    CatalogField,
    CatalogReport,
    CatalogScenario,
    REPORT_READINESS,
    REPORT_SOURCES,
    report_title,
)

_SAMPLE_REQUEST_ID = "7c2e1a8f-4b0d-4e9a-9f31-2a6c8d5e1b04"
_SAMPLE_CANDIDATE_ID = "cnd.opaque.token.example"

_SAMPLE_SUBJECT: dict[str, Any] = {
    "FIRST_NAME": "Kevin",
    "LAST_NAME": "Jackson",
    "DATE_OF_BIRTH": "1969-02-10T00:00:00",
    "PLACE_OF_BIRTH": "VA",
    "SEX": "M",
    "CITIZENSHIP": "USA",
    "MARITAL_STATUS": "M",
    "UPDATED_TS": "2026-09-01T12:00:00",
    "RECORD_VERSION": "1",
}

_SAMPLE_ROWS: dict[str, dict[str, Any]] = {
    "identity": dict(_SAMPLE_SUBJECT),
    "status": {
        "ORG_CODE": "DCSA",
        "POSITION_TITLE": "Analyst",
        "DUTY_LOCATION": "Quantico, VA",
        "RISK_TIER": "M",
        "ELIGIBILITY_LEVEL": "S",
        "STATUS_CODE": "ELIGIBLE",
        "STATUS_EFFECTIVE_DATE": "2024-06-01",
        "UPDATED_TS": "2026-09-01T12:00:00",
        "RECORD_VERSION": "1",
    },
    "check": {
        "CHECK_ID": "CHK-1001",
        "LOCATION_CODE": "QAN",
        "CHECK_TYPE": "NACI",
        "RESULT_CODE": "FAVORABLE",
        "RESULT_SCORE": "0",
        "CHECKED_TS": "2024-05-15T08:00:00",
        "LOAD_SEQ": "12",
    },
    "activity": {
        "ACTIVITY_ID": "ACT-2001",
        "LOCATION_CODE": "QAN",
        "ACTIVITY_TYPE": "INVESTIGATION",
        "DETAIL": "Case opened",
        "EVENT_TS": "2024-04-02T14:30:00",
        "LOAD_SEQ": "8",
    },
    "signal": {
        "SIGNAL_ID": "SIG-3001",
        "LOCATION_CODE": "QAN",
        "SIGNAL_TYPE": "CV_ALERT",
        "SEVERITY": "LOW",
        "SIGNAL_TS": "2025-11-03T09:12:00",
        "LOAD_SEQ": "3",
    },
}


def _json_type(schema: dict[str, Any]) -> tuple[str, bool]:
    """Map a Pydantic JSON-schema property to a catalog type.

    Args:
        schema: JSON Schema fragment for one field.

    Returns:
        JSON type name and whether the field is nullable.
    """
    if "anyOf" in schema:
        types = [item.get("type", "string") for item in schema["anyOf"] if item.get("type") != "null"]
        nullable = any(item.get("type") == "null" for item in schema["anyOf"])
        return (types[0] if types else "string"), nullable
    return str(schema.get("type") or "string"), schema.get("type") == "null"


def _fields_for_section(section: str) -> list[CatalogField]:
    """List public JSON fields for one report section.

    Args:
        section: Logical source name.

    Returns:
        Catalog field metadata.
    """
    model = SECTION_ROW_MODELS[section]
    props = model.model_json_schema().get("properties") or {}
    required = set(model.model_json_schema().get("required") or [])
    fields: list[CatalogField] = []
    for name, spec in props.items():
        json_type, nullable = _json_type(spec)
        fields.append(
            CatalogField(
                name=name,
                type=json_type,
                nullable=nullable or name not in required,
            )
        )
    return fields


def _example_envelope(code: ReportCode) -> dict[str, Any]:
    """Build a sample nested report body for one FPVR code.

    Args:
        code: FPVR report code.

    Returns:
        Example JSON matching ``FPVRReportResponse``.
    """
    data = {source: [_SAMPLE_ROWS[source]] for source in REPORT_SOURCES[code]}
    return {
        "code": code.value,
        "title": report_title(code),
        "subject": dict(_SAMPLE_SUBJECT),
        "data": data,
    }


def build_catalog() -> ApiCatalog:
    """Return the full caller catalog.

    Returns:
        Typed catalog of APIs, scenarios, and per-report schemas.
    """
    reports = []
    for code in ReportCode:
        sources = list(REPORT_SOURCES[code])
        reports.append(
            CatalogReport(
                report_code=code,
                title=report_title(code),
                sources=sources,
                tables=[get_settings().source_table(s) for s in sources],
                readiness=REPORT_READINESS[code],
                data_fields={s: _fields_for_section(s) for s in sources},
                example_response=_example_envelope(code),
            )
        )

    create_body = {
        "report_code": "FPVR-6",
        "first_name": "Kevin",
        "last_name": "Jackson",
        "date_of_birth": "1969-02-10",
    }
    accepted = {
        "request_id": _SAMPLE_REQUEST_ID,
        "status": "ready",
        "requested_at": "2026-10-01T16:00:00Z",
        "requested_by": "sp-client-id",
        "resolution_method": "unique_match",
        "report": _example_envelope(ReportCode.FPVR_6),
    }
    pending = {
        "request_id": _SAMPLE_REQUEST_ID,
        "status": "pending",
        "requested_at": "2026-10-01T16:00:00Z",
        "requested_by": "sp-client-id",
        "resolution_method": "unique_match",
        "report": None,
    }

    try:
        oidc_path = f"{workspace_host()}/oidc/v1/token"
    except WarehouseNotConfiguredError:
        oidc_path = "https://<workspace-host>/oidc/v1/token"

    apis = [
        CatalogApi(
            id="token",
            method="POST",
            path=oidc_path,
            auth="HTTP Basic (client_id:client_secret). This is the workspace OIDC endpoint, not this app.",
            summary=(
                "Mint a Databricks access token with OAuth2 client_credentials "
                "before calling this app. The app has no /oauth/token route."
            ),
            request_body={
                "grant_type": "client_credentials",
                "scope": "all-apis",
            },
            scenarios=[
                CatalogScenario(
                    id="token_ok",
                    http_status=200,
                    summary="Credentials accepted. Send access_token as Authorization: Bearer on app APIs.",
                    response={
                        "access_token": "<databricks-token>",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                    },
                ),
                CatalogScenario(
                    id="token_unauthorized",
                    http_status=401,
                    summary="Invalid client_id or client_secret.",
                    response={"error": "invalid_client"},
                ),
            ],
        ),
        CatalogApi(
            id="request",
            method="POST",
            path="/api/v1/requests",
            auth="Bearer (workspace OIDC token)",
            summary=(
                "Resolve a subject and open one official FPVR request. SSN is "
                "optional when first_name + last_name + date_of_birth is unique."
            ),
            request_body=create_body,
            scenarios=[
                CatalogScenario(
                    id="unique_match",
                    http_status=201,
                    summary="Exactly one subject matched; request_id issued. report is included when ready.",
                    request=create_body,
                    response=accepted,
                ),
                CatalogScenario(
                    id="candidate_resubmit",
                    http_status=200,
                    summary="Caller resubmits an opaque candidate_id from a prior 409.",
                    request={"report_code": "FPVR-6", "candidate_id": _SAMPLE_CANDIDATE_ID},
                    response={**accepted, "resolution_method": "candidate_id"},
                ),
                CatalogScenario(
                    id="ambiguous",
                    http_status=409,
                    summary="Two or more subjects matched. No request_id. SSN is not returned.",
                    request=create_body,
                    response={
                        "detail": (
                            "Multiple subjects matched; provide more information or candidate_id"
                        ),
                        "total": 2,
                        "candidates": [
                            {
                                "candidate_id": _SAMPLE_CANDIDATE_ID,
                                "FIRST_NAME": "Kevin",
                                "LAST_NAME": "Jackson",
                                "DATE_OF_BIRTH": "1969-02-10T00:00:00",
                                "PLACE_OF_BIRTH": "VA",
                                "SEX": "M",
                                "CITIZENSHIP": "USA",
                                "MARITAL_STATUS": "M",
                            }
                        ],
                    },
                ),
                CatalogScenario(
                    id="not_found",
                    http_status=404,
                    summary="No subject matched. Nothing is written to the request log.",
                    request=create_body,
                    response={"detail": "No subject matched the supplied identity"},
                ),
                CatalogScenario(
                    id="missing_identity",
                    http_status=400,
                    summary="Body has neither candidate_id nor any identity field.",
                    request={"report_code": "FPVR-6"},
                    response={
                        "detail": [
                            {
                                "type": "value_error",
                                "msg": (
                                    "Value error, Provide candidate_id, ssn, or "
                                    "first_name/last_name/date_of_birth"
                                ),
                            }
                        ]
                    },
                ),
                CatalogScenario(
                    id="unauthorized",
                    http_status=401,
                    summary="Missing or invalid caller token.",
                    response={"detail": "Missing user access token for OBO SQL."},
                ),
            ],
        ),
        CatalogApi(
            id="get",
            method="GET",
            path="/api/v1/requests/{request_id}",
            auth="Bearer (OBO SQL; ABAC/RBAC applied when assembling report)",
            summary=(
                "Return the same body as POST. Pending reports re-check the lake "
                "and may flip to ready with report set. SSN is never returned."
            ),
            request_body=None,
            scenarios=[
                CatalogScenario(
                    id="pending",
                    http_status=200,
                    summary="Report not yet servable (typical for FPVR-2/3/7). report is null.",
                    response=pending,
                ),
                CatalogScenario(
                    id="ready",
                    http_status=200,
                    summary="Same envelope as POST 201; report is populated.",
                    response=accepted,
                ),
                CatalogScenario(
                    id="not_found",
                    http_status=404,
                    summary="Unknown request_id (or not visible to this caller).",
                    response={"detail": "Request not found"},
                ),
            ],
        ),
    ]

    return ApiCatalog(
        title="DCSA FPVR API catalog",
        version=__version__,
        apis=apis,
        reports=reports,
        notes=[
            "Call POST {workspace}/oidc/v1/token with HTTP Basic (client_id:client_secret) "
            "and grant_type=client_credentials, then Authorization: Bearer <access_token> on this app.",
            "Official requests are logged as the app service principal to "
            "dcsa_catalog.dcsa_api.api_request_log.",
            "Subject and report SELECT statements run on-behalf-of the caller.",
            "SSN is an internal join key only; it is not returned on candidates or request bodies.",
            "Interactive docs: /docs  ·  ReDoc: /redoc  ·  This catalog JSON: /api/v1/catalog",
        ],
    )
