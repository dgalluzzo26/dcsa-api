"""FastAPI entrypoint for the DCSA Databricks App.

Builds the ``app`` object served by uvicorn (see ``app.yaml``) and mounts all
API routes under ``/api``.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app import __version__
from app.core.config import get_settings
from app.core.http_logging import RequestIdMiddleware, configure_logging, current_request_id
from app.routes import router
from app.routes.catalog import help_page

configure_logging()
settings = get_settings()

app = FastAPI(
    title="DCSA API",
    description=(
        "Backend FastAPI service for DCSA on Databricks Apps.\n\n"
        "## Docs\n"
        "- FPVR catalog (schemas + scenarios): [`/api/v1/catalog`](/api/v1/catalog)\n"
        "- Human-readable help: [`/help`](/help)\n"
        "- Interactive Swagger UI: [`/docs`](/docs)\n"
        "- ReDoc: [`/redoc`](/redoc)\n"
        "- OpenAPI JSON: [`/openapi.json`](/openapi.json)\n\n"
        "Layering: **routes** (HTTP) → **services** (business logic) → **models** (schemas)."
    ),
    version=__version__,
    contact={"name": "DCSA API"},
    swagger_ui_parameters={"persistAuthorization": True},
    openapi_tags=[
        {"name": "system", "description": "Health and identity"},
        {
            "name": "subject-identity",
            "description": "Look up dcsa_catalog.edladmin.subject_identity via OBO SQL",
        },
        {
            "name": "fpvr-requests",
            "description": "Official FPVR request create and get",
        },
        {
            "name": "catalog",
            "description": "Exact request/response schemas and scenarios for configured reports",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return 400 for invalid or incomplete request bodies and query params.

    FastAPI defaults these to 422; this API treats them as bad requests.
    """
    rid = current_request_id(request)
    return JSONResponse(
        status_code=400,
        content={"detail": jsonable_encoder(exc.errors()), "request_id": rid},
        headers={"X-Request-Id": rid},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Attach ``request_id`` to HTTP error bodies for log correlation.

    Args:
        request: Incoming request.
        exc: Raised HTTP error.

    Returns:
        JSON body with ``detail`` and ``request_id``.
    """
    rid = current_request_id(request)
    detail = exc.detail
    if isinstance(detail, dict):
        content: dict = {**jsonable_encoder(detail), "request_id": rid}
    else:
        content = {"detail": jsonable_encoder(detail), "request_id": rid}
    headers = dict(exc.headers or {})
    headers["X-Request-Id"] = rid
    return JSONResponse(status_code=exc.status_code, content=content, headers=headers)


def custom_openapi() -> dict:
    """Build OpenAPI with validation failures documented as 400, not 422."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
        contact=app.contact,
    )
    for item in schema.get("paths", {}).values():
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses")
            if not responses or "422" not in responses:
                continue
            moved = responses.pop("422")
            if moved.get("description") in {"Validation Error", "Unprocessable Content"}:
                moved["description"] = "Bad Request"
            responses.setdefault("400", moved)
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi

app.include_router(router, prefix="/api")
app.add_api_route("/help", help_page, methods=["GET"], include_in_schema=False)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    """Return service metadata and links to the API documentation.

    Returns:
        App name, version, and paths to the docs and health endpoints.
    """
    return {
        "app": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "redoc": "/redoc",
        "help": "/help",
        "catalog": "/api/v1/catalog",
        "openapi": "/openapi.json",
        "health": "/api/health",
    }
