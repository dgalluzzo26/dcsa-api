"""Shared settings and Databricks client helpers."""

from __future__ import annotations

import os
import re
from functools import lru_cache

from pydantic import BaseModel, Field

from app.models.report_contract import SECTION_TABLES

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")
_SCHEMA = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
_FQ_TABLE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+){2}$")

_SECTION_ENV = {
    "identity": "DCSA_TABLE_IDENTITY",
    "status": "DCSA_TABLE_STATUS",
    "check": "DCSA_TABLE_CHECK",
    "activity": "DCSA_TABLE_ACTIVITY",
    "signal": "DCSA_TABLE_SIGNAL",
}


def qualify_uc_name(name: str, catalog_schema: str) -> str:
    """Resolve a table or view name against ``catalog.schema``.

    ``name`` may be ``table``, ``schema.table``, or ``catalog.schema.table``.
    Views and tables use the same three-part identifier.

    Args:
        name: Object name from configuration.
        catalog_schema: Default ``catalog.schema``.

    Returns:
        Fully qualified ``catalog.schema.table`` identifier.

    Raises:
        ValueError: If ``name`` or ``catalog_schema`` is not a valid identifier.
    """
    raw = name.strip()
    if not raw:
        raise ValueError("Table or view name is empty")
    if not _SCHEMA.match(catalog_schema):
        raise ValueError(f"Invalid catalog schema: {catalog_schema!r}")
    parts = raw.split(".")
    if not all(_IDENT.match(part) for part in parts):
        raise ValueError(f"Invalid table or view name: {name!r}")
    if len(parts) == 3:
        return raw
    if len(parts) == 2:
        catalog = catalog_schema.split(".", 1)[0]
        return f"{catalog}.{raw}"
    if len(parts) == 1:
        return f"{catalog_schema}.{raw}"
    raise ValueError(f"Invalid table or view name: {name!r}")


class Settings(BaseModel):
    """Application settings loaded from environment variables.

    Attributes:
        app_name: Application name (``DCSA_APP_NAME``).
        environment: Deployment environment (``DCSA_ENV``).
        warehouse_id: SQL warehouse id for OBO queries (``DATABRICKS_WAREHOUSE_ID``).
        subject_identity_table: Fully qualified identity table or view
            (``DCSA_SUBJECT_IDENTITY_TABLE`` or ``DCSA_TABLE_IDENTITY``).
        request_log_table: Fully qualified request log table written by the
            app service principal (``DCSA_REQUEST_LOG_TABLE``).
        catalog_schema: Default Unity Catalog ``catalog.schema`` for FPVR
            sources (``DCSA_CATALOG_SCHEMA``). Change this to retarget the demo
            at another catalog or schema.
        table_identity: Identity object name (``DCSA_TABLE_IDENTITY``).
        table_status: Status object name (``DCSA_TABLE_STATUS``).
        table_check: Check object name (``DCSA_TABLE_CHECK``).
        table_activity: Activity object name (``DCSA_TABLE_ACTIVITY``).
        table_signal: Signal object name (``DCSA_TABLE_SIGNAL``).
    """

    app_name: str = Field(default_factory=lambda: os.getenv("DCSA_APP_NAME", "dcsa-api"))
    environment: str = Field(default_factory=lambda: os.getenv("DCSA_ENV", "dev"))
    warehouse_id: str = Field(
        default_factory=lambda: os.getenv("DATABRICKS_WAREHOUSE_ID", "c56ad4dc84dcac90").strip()
    )
    catalog_schema: str = Field(
        default_factory=lambda: os.getenv(
            "DCSA_CATALOG_SCHEMA",
            "dcsa_catalog.edladmin",
        ).strip()
    )
    table_identity: str = Field(
        default_factory=lambda: os.getenv("DCSA_TABLE_IDENTITY", SECTION_TABLES["identity"]).strip()
    )
    table_status: str = Field(
        default_factory=lambda: os.getenv("DCSA_TABLE_STATUS", SECTION_TABLES["status"]).strip()
    )
    table_check: str = Field(
        default_factory=lambda: os.getenv("DCSA_TABLE_CHECK", SECTION_TABLES["check"]).strip()
    )
    table_activity: str = Field(
        default_factory=lambda: os.getenv("DCSA_TABLE_ACTIVITY", SECTION_TABLES["activity"]).strip()
    )
    table_signal: str = Field(
        default_factory=lambda: os.getenv("DCSA_TABLE_SIGNAL", SECTION_TABLES["signal"]).strip()
    )
    request_log_table: str = Field(
        default_factory=lambda: os.getenv(
            "DCSA_REQUEST_LOG_TABLE",
            "dcsa_catalog.dcsa_api.api_request_log",
        ).strip()
    )

    @property
    def subject_identity_table(self) -> str:
        """Return the fully qualified identity table or view.

        ``DCSA_SUBJECT_IDENTITY_TABLE`` wins when it is a three-part name so
        existing deployments keep working. Otherwise the identity object is
        resolved from ``DCSA_TABLE_IDENTITY`` and ``DCSA_CATALOG_SCHEMA``.

        Returns:
            ``catalog.schema.table`` for identity lookups.
        """
        override = os.getenv("DCSA_SUBJECT_IDENTITY_TABLE", "").strip()
        if _FQ_TABLE.match(override):
            return override
        return qualify_uc_name(self.table_identity, self.catalog_schema)

    def source_table(self, section: str) -> str:
        """Return the fully qualified table or view for one FPVR section.

        Args:
            section: Logical source name (identity, status, check, activity, signal).

        Returns:
            ``catalog.schema.table`` (or view) to query.

        Raises:
            KeyError: If ``section`` is not a known source.
        """
        if section == "identity":
            return self.subject_identity_table
        env_name = _SECTION_ENV[section]
        raw = os.getenv(env_name, getattr(self, f"table_{section}")).strip()
        return qualify_uc_name(raw, self.catalog_schema)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, read from the environment once.

    Returns:
        The cached ``Settings`` instance.
    """
    return Settings()
