"""FastAPI entrypoint for the DCSA Databricks App."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import get_settings
from app.routes import router

settings = get_settings()

app = FastAPI(
    title="DCSA API",
    description=(
        "Backend FastAPI service for DCSA on Databricks Apps.\n\n"
        "## Docs\n"
        "- Interactive Swagger UI: [`/docs`](/docs)\n"
        "- ReDoc: [`/redoc`](/redoc)\n"
        "- OpenAPI JSON: [`/openapi.json`](/openapi.json)\n\n"
        "Layering: **routes** (HTTP) → **services** (business logic) → **models** (schemas)."
    ),
    version=__version__,
    contact={"name": "DCSA API"},
    openapi_tags=[
        {"name": "system", "description": "Health and identity"},
        {"name": "records", "description": "Sample domain CRUD (swap store for UC/Lakebase later)"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "app": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
        "health": "/api/health",
    }
