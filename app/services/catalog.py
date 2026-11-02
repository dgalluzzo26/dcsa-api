"""Build the public FPVR API catalog from the report contract."""

from __future__ import annotations

from typing import Any

from app import __version__
from app.core.config import ReportConfig, get_settings, normalize_report_code
from app.models.dto.fpvr6 import IdentityDto, StatusDto
from app.services.dto_fpvr6 import map_report
from app.core.sql import WarehouseNotConfiguredError, workspace_host
from app.models.report_contract import (
    SECTION_ROW_MODELS,
    ApiCatalog,
    CatalogApi,
    CatalogField,
    CatalogReport,
    CatalogScenario,
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


def _public_columns(source_name: str) -> list[str]:
    """Return JSON columns for a source (configured columns minus omitted).

    Args:
        source_name: YAML source key.

    Returns:
        Public column names in SELECT order.
    """
    source = get_settings().sources[source_name]
    omit = set(source.omit_from_output)
    return [name for name in source.columns if name not in omit]


def _fields_for_source(source_name: str) -> list[CatalogField]:
    """List public JSON fields for one configured source.

    Args:
        source_name: YAML source key.

    Returns:
        Catalog field metadata.
    """
    public = _public_columns(source_name)
    model = SECTION_ROW_MODELS.get(source_name)
    schema_fields: dict[str, CatalogField] = {}
    if model is not None:
        props = model.model_json_schema().get("properties") or {}
        required = set(model.model_json_schema().get("required") or [])
        for name, spec in props.items():
            json_type, nullable = _json_type(spec)
            schema_fields[name] = CatalogField(
                name=name,
                type=json_type,
                nullable=nullable or name not in required,
            )
    fields: list[CatalogField] = []
    for name in public:
        if name in schema_fields:
            fields.append(schema_fields[name])
        else:
            fields.append(CatalogField(name=name, type="string", nullable=True))
    return fields


def _fields_from_model(model: type) -> list[CatalogField]:
    """List catalog fields from a DTO Pydantic model."""
    schema = model.model_json_schema()
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
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


def _sample_row(source_name: str) -> dict[str, Any]:
    """Return a public warehouse-shaped sample row for one YAML source."""
    source = get_settings().sources[source_name]
    omit = set(source.omit_from_output)
    sample = dict(_SAMPLE_ROWS.get(source_name) or {})
    return {name: sample.get(name) for name in source.columns if name not in omit}


def _readiness_summary(report: ReportConfig) -> str:
    """Human-readable readiness rule for the catalog."""
    readiness = report.readiness
    if readiness.mode == "always":
        return "always"
    if readiness.mode == "section_non_empty":
        return f"ready when {readiness.section} is non-empty"
    if readiness.mode == "any_section_non_empty":
        return f"ready when any of {', '.join(readiness.sections or [])} is non-empty"
    if readiness.mode == "all_sections_non_empty":
        return f"ready when all of {', '.join(readiness.sections or [])} are non-empty"
    return f"ready when {readiness.section}.{readiness.field} is present"


def _example_envelope(code: str) -> dict[str, Any]:
    """Build a sample nested report body for one FPVR code.

    Args:
        code: Normalized report code.

    Returns:
        Example JSON matching the public report envelope.
    """
    settings = get_settings()
    code = normalize_report_code(code)
    report = settings.reports[code]
    data = {
        section_name: [_sample_row(section.source)]
        for section_name, section in report.sections.items()
    }
    envelope = {
        "code": code,
        "title": report.name,
        "subject": dict(_SAMPLE_SUBJECT),
        "data": data,
    }
    if normalize_report_code(code) == "fpvr6":
        return map_report(envelope)
    return envelope


def build_catalog() -> ApiCatalog:
    """Return the full caller catalog.

    Returns:
        Typed catalog of APIs, scenarios, and per-report schemas.
    """
    settings = get_settings()
    reports = []
    for code, report in settings.reports.items():
        source_names = [section.source for section in report.sections.values()]
        if normalize_report_code(code) == "fpvr6":
            data_fields = {
                "identity": _fields_from_model(IdentityDto),
                "status": _fields_from_model(StatusDto),
            }
            tables: list[str] = []
        else:
            data_fields = {
                section_name: _fields_for_source(section.source)
                for section_name, section in report.sections.items()
            }
            tables = [settings.source_table(name) for name in source_names]
        reports.append(
            CatalogReport(
                report_code=code,
                title=report.name,
                sources=source_names,
                tables=tables,
                readiness=_readiness_summary(report),
                data_fields=data_fields,
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
        "report": _example_envelope("fpvr6"),
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
