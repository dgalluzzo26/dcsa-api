"""FastAPI entrypoint for the DCSA Databricks App.

Builds the ``app`` object served by uvicorn (see ``app.yaml``) and mounts all
API routes under ``/api``.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
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
            "description": "Exact request/response schemas and scenarios for FPVR-1 through FPVR-7",
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
        content: dict = {**detail, "request_id": rid}
    else:
        content = {"detail": detail, "request_id": rid}
    headers = dict(exc.headers or {})
    headers["X-Request-Id"] = rid
    return JSONResponse(status_code=exc.status_code, content=content, headers=headers)

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
