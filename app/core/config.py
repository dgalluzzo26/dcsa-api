"""Shared settings and Databricks client helpers."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")
_SCHEMA = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
_REPORT_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CONFIG_PATH = Path("report-config.yaml")


def _normalize_workspace_host(value: str) -> str:
    """Return an absolute workspace URL with no trailing slash.

    Args:
        value: Host or URL from YAML or ``DATABRICKS_HOST``.

    Returns:
        Normalized ``https://`` (or ``http://``) workspace URL.

    Raises:
        ValueError: If ``value`` is empty.
    """
    host = value.strip().rstrip("/")
    if not host:
        raise ValueError("Databricks workspace host is empty")
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return host


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


def _require_ident(value: str, *, kind: str) -> str:
    """Reject names that cannot be interpolated as SQL identifiers.

    Args:
        value: Candidate identifier.
        kind: Label used in the error message.

    Returns:
        The stripped identifier.

    Raises:
        ValueError: If ``value`` is not a safe identifier.
    """
    raw = value.strip()
    if not _IDENT.match(raw):
        raise ValueError(f"Invalid {kind}: {value!r}")
    return raw


class ApplicationConfig(BaseModel):
    """Application metadata from the YAML file."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    environment: str = Field(min_length=1)


class DatabricksConfig(BaseModel):
    """Databricks connection and persistence settings from YAML."""

    model_config = ConfigDict(str_strip_whitespace=True)

    host: str = Field(min_length=1)
    warehouse_id: str = Field(min_length=1)
    default_catalog_schema: str = Field(min_length=1)
    request_log_table: str = Field(min_length=1)

    @field_validator("host")
    @classmethod
    def host_is_url(cls, value: str) -> str:
        """Require a usable workspace URL."""
        return _normalize_workspace_host(value)


class FilterConfig(BaseModel):
    """Parameterized equality filter used to select rows for one source."""

    model_config = ConfigDict(str_strip_whitespace=True)

    column: str = Field(min_length=1)
    parameter: Literal["subject_ssn"]

    @field_validator("column")
    @classmethod
    def column_is_identifier(cls, value: str) -> str:
        """Require the filter column to be a SQL identifier."""
        return _require_ident(value, kind="filter column")


class SourceConfig(BaseModel):
    """One reusable Unity Catalog table or view a report can query."""

    model_config = ConfigDict(str_strip_whitespace=True)

    table: str = Field(min_length=1)
    filter: FilterConfig
    columns: list[str] = Field(min_length=1)
    omit_from_output: list[str] = Field(default_factory=list)

    @field_validator("columns", "omit_from_output")
    @classmethod
    def names_are_identifiers(cls, values: list[str]) -> list[str]:
        """Require every listed column name to be a SQL identifier."""
        return [_require_ident(value, kind="column") for value in values]

    @model_validator(mode="after")
    def validate_column_lists(self) -> "SourceConfig":
        """Require filter/omit columns to be selected."""
        selected = set(self.columns)
        if self.filter.column not in selected:
            raise ValueError(
                f"Filter column {self.filter.column!r} is not in source columns"
            )
        unknown = [name for name in self.omit_from_output if name not in selected]
        if unknown:
            raise ValueError(f"omit_from_output columns are not selected: {unknown}")
        return self


class ReportSectionConfig(BaseModel):
    """One named section in a report payload."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source: str = Field(min_length=1)

    @field_validator("source")
    @classmethod
    def source_is_identifier(cls, value: str) -> str:
        """Require the section source key to be a safe identifier."""
        return _require_ident(value, kind="source name")


class ReadinessConfig(BaseModel):
    """Declarative ready/pending rule for one report."""

    model_config = ConfigDict(str_strip_whitespace=True)

    mode: Literal["always", "section_non_empty", "any_section_non_empty", "field_present"]
    section: str | None = None
    sections: list[str] | None = None
    field: str | None = None

    @model_validator(mode="after")
    def validate_mode_fields(self) -> "ReadinessConfig":
        """Require the arguments that each readiness mode needs."""
        if self.mode == "always":
            return self
        if self.mode == "section_non_empty":
            if not self.section:
                raise ValueError("section_non_empty readiness requires section")
            return self
        if self.mode == "any_section_non_empty":
            if not self.sections:
                raise ValueError("any_section_non_empty readiness requires sections")
            return self
        if not self.section or not self.field:
            raise ValueError("field_present readiness requires section and field")
        _require_ident(self.field, kind="readiness field")
        return self


class ReportConfig(BaseModel):
    """One requestable report assembled from named sources."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    sections: dict[str, ReportSectionConfig] = Field(min_length=1)
    readiness: ReadinessConfig

    @field_validator("sections")
    @classmethod
    def section_names_are_identifiers(
        cls, value: dict[str, ReportSectionConfig]
    ) -> dict[str, ReportSectionConfig]:
        """Require section keys to be safe identifiers."""
        for name in value:
            _require_ident(name, kind="section name")
        return value


class YamlConfig(BaseModel):
    """Validated ``report-config.yaml`` document."""

    version: Literal[1]
    application: ApplicationConfig
    databricks: DatabricksConfig
    sources: dict[str, SourceConfig]
    reports: dict[str, ReportConfig]

    @field_validator("sources")
    @classmethod
    def source_names_are_identifiers(
        cls, value: dict[str, SourceConfig]
    ) -> dict[str, SourceConfig]:
        """Require source keys to be safe identifiers."""
        for name in value:
            _require_ident(name, kind="source name")
        return value

    @field_validator("reports")
    @classmethod
    def report_codes_are_safe(cls, value: dict[str, ReportConfig]) -> dict[str, ReportConfig]:
        """Require report codes to be non-empty safe tokens."""
        if not value:
            raise ValueError("At least one report must be configured")
        for code in value:
            if not _REPORT_CODE.match(code.strip()):
                raise ValueError(f"Invalid report code: {code!r}")
        return value

    @model_validator(mode="after")
    def validate_cross_references(self) -> "YamlConfig":
        """Require identity plus consistent report/source/readiness references."""
        if "identity" not in self.sources:
            raise ValueError("An identity source is required for subject lookup")
        for code, report in self.reports.items():
            for section_name, section in report.sections.items():
                if section.source not in self.sources:
                    raise ValueError(
                        f"Report {code} section {section_name} references "
                        f"unknown source {section.source!r}"
                    )
            _validate_readiness(code, report, self.sources)
        return self


def _validate_readiness(
    code: str, report: ReportConfig, sources: dict[str, SourceConfig]
) -> None:
    """Ensure readiness points at sections and fields that exist on the report.

    Args:
        code: Report code, used in error messages.
        report: Report being validated.
        sources: Configured sources.

    Raises:
        ValueError: If readiness references are invalid.
    """
    readiness = report.readiness
    section_names = set(report.sections)
    if readiness.mode == "always":
        return
    if readiness.mode == "section_non_empty":
        if readiness.section not in section_names:
            raise ValueError(
                f"Report {code} readiness section {readiness.section!r} is not assembled"
            )
        return
    if readiness.mode == "any_section_non_empty":
        unknown = [name for name in (readiness.sections or []) if name not in section_names]
        if unknown:
            raise ValueError(f"Report {code} readiness sections are not assembled: {unknown}")
        return
    if readiness.section not in section_names:
        raise ValueError(
            f"Report {code} readiness section {readiness.section!r} is not assembled"
        )
    source = sources[report.sections[readiness.section].source]
    if readiness.field not in source.columns:
        raise ValueError(
            f"Report {code} readiness field {readiness.field!r} is not a column of "
            f"{report.sections[readiness.section].source}"
        )
    if readiness.field in source.omit_from_output:
        raise ValueError(
            f"Report {code} readiness field {readiness.field!r} is omitted from output"
        )


class Settings(BaseModel):
    """Process settings loaded from ``report-config.yaml``.

    ``DATABRICKS_HOST`` and ``DATABRICKS_WAREHOUSE_ID`` override YAML when set.
    Databricks Apps typically injects both.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    app_name: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    workspace_host: str = Field(min_length=1)
    warehouse_id: str = Field(min_length=1)
    catalog_schema: str = Field(min_length=1)
    request_log_table: str = Field(min_length=1)
    sources: dict[str, SourceConfig]
    reports: dict[str, ReportConfig]

    @property
    def subject_identity_table(self) -> str:
        """Return the fully qualified identity table or view.

        Returns:
            ``catalog.schema.table`` for identity lookups.
        """
        return self.source_table("identity")

    def source_table(self, section: str) -> str:
        """Return the fully qualified table or view for one configured source.

        Args:
            section: Logical source name.

        Returns:
            ``catalog.schema.table`` (or view) to query.

        Raises:
            KeyError: If ``section`` is not a known source.
        """
        source = self.sources[section]
        return qualify_uc_name(source.table, self.catalog_schema)

    def report_title(self, report_code: str) -> str:
        """Return the display name for a configured report.

        Args:
            report_code: YAML report key.

        Returns:
            Human-readable report name.

        Raises:
            KeyError: If ``report_code`` is not configured.
        """
        return self.reports[report_code].name


@lru_cache
def get_settings() -> Settings:
    """Load and cache process-wide settings from the repository YAML file.

    Returns:
        The cached ``Settings`` instance.
    """
    with _CONFIG_PATH.open(encoding="utf-8") as config_file:
        config = YamlConfig.model_validate(yaml.safe_load(config_file))

    injected_host = os.getenv("DATABRICKS_HOST", "").strip()
    injected_warehouse = os.getenv("DATABRICKS_WAREHOUSE_ID", "").strip()
    return Settings(
        app_name=config.application.name,
        environment=config.application.environment,
        workspace_host=_normalize_workspace_host(injected_host or config.databricks.host),
        warehouse_id=injected_warehouse or config.databricks.warehouse_id,
        catalog_schema=config.databricks.default_catalog_schema,
        request_log_table=config.databricks.request_log_table,
        sources=config.sources,
        reports=config.reports,
    )
