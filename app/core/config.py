"""Shared settings and Databricks client helpers."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Application settings loaded from environment variables.

    Attributes:
        app_name: Application name (``DCSA_APP_NAME``).
        environment: Deployment environment (``DCSA_ENV``).
        warehouse_id: SQL warehouse id for OBO queries (``DATABRICKS_WAREHOUSE_ID``).
        subject_identity_table: Fully qualified subject identity table
            (``DCSA_SUBJECT_IDENTITY_TABLE``).
    """

    app_name: str = Field(default_factory=lambda: os.getenv("DCSA_APP_NAME", "dcsa-api"))
    environment: str = Field(default_factory=lambda: os.getenv("DCSA_ENV", "dev"))
    warehouse_id: str = Field(
        default_factory=lambda: os.getenv("DATABRICKS_WAREHOUSE_ID", "c56ad4dc84dcac90").strip()
    )
    subject_identity_table: str = Field(
        default_factory=lambda: os.getenv(
            "DCSA_SUBJECT_IDENTITY_TABLE",
            "dcsa_catalog.edladmin.subject_identity",
        ).strip()
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read from the environment once.

    Returns:
        The cached ``Settings`` instance.
    """
    return Settings()
