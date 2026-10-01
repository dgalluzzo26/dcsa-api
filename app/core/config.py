"""Shared settings and Databricks client helpers."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = Field(default_factory=lambda: os.getenv("DCSA_APP_NAME", "dcsa-api"))
    environment: str = Field(default_factory=lambda: os.getenv("DCSA_ENV", "dev"))
    warehouse_id: str = Field(
        default_factory=lambda: os.getenv("DATABRICKS_WAREHOUSE_ID", "").strip()
    )
    use_memory_store: bool = Field(
        default_factory=lambda: os.getenv("DCSA_USE_MEMORY_STORE", "true").lower()
        in ("1", "true", "yes")
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_workspace_client():
    """App SP via SDK Config() — uses injected DATABRICKS_* in Databricks Apps."""
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()
