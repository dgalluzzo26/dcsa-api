"""Shared settings and Databricks client helpers."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator, AfterValidator
from enum import Enum

_IDENT = re.compile(r"^[A-Za-z0-9_]+$")
_SCHEMA = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
_REPORT_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_CONFIG_PATH = Path("config.yaml")
_MAPPING_PATH = Path("mapping.yml")
_JOB_PARAM_TOKEN = re.compile(r"^\{\{([a-z_]+)\}\}$")
_ALLOWED_JOB_PARAM_TOKENS = frozenset(
    {
        "request_id",
        "report_code",
        "subject_ssn",
        "subject_first_name",
        "subject_last_name",
        "subject_date_of_birth",
    }
)


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


def qualify_uc_name(
    name: str,
    catalog_schema: str,
    catalog: str | None = None,
    schema: str | None = None,
) -> str:
    """Resolve a table or view name against ``catalog.schema``.

    ``name`` may be ``table``, ``schema.table``, or ``catalog.schema.table``.
    Views and tables use the same three-part identifier. Optional ``catalog``
    and ``schema`` replace the matching parts of ``catalog_schema``. They
    cannot overlap parts already present in ``name``.

    Args:
        name: Object name from configuration.
        catalog_schema: Default ``catalog.schema``.
        catalog: Optional Unity Catalog catalog that replaces the default.
        schema: Optional Unity Catalog schema that replaces the default.

    Returns:
        Fully qualified ``catalog.schema.table`` identifier.

    Raises:
        ValueError: If ``name``, ``catalog_schema``, ``catalog``, or ``schema``
            is invalid.
    """
    raw = name.strip()
    if not raw:
        raise ValueError("Table or view name is empty")
    if not _SCHEMA.match(catalog_schema):
        raise ValueError(f"Invalid catalog schema: {catalog_schema!r}")
    default_catalog, default_schema = catalog_schema.split(".", 1)
    catalog_override = None if catalog is None else _require_ident(catalog, kind="catalog")
    schema_override = None if schema is None else _require_ident(schema, kind="schema")
    parts = raw.split(".")
    if not all(_IDENT.match(part) for part in parts):
        raise ValueError(f"Invalid table or view name: {name!r}")
    if len(parts) == 3:
        if catalog_override is not None:
            raise ValueError(
                f"catalog override {catalog_override!r} cannot be used with a "
                f"fully qualified table name: {name!r}"
            )
        if schema_override is not None:
            raise ValueError(
                f"schema override {schema_override!r} cannot be used with a "
                f"fully qualified table name: {name!r}"
            )
        return raw
    resolved_catalog = catalog_override or default_catalog
    if len(parts) == 2:
        if schema_override is not None:
            raise ValueError(
                f"schema override {schema_override!r} cannot be used with a "
                f"schema-qualified table name: {name!r}"
            )
        return f"{resolved_catalog}.{raw}"
    if len(parts) == 1:
        resolved_schema = schema_override or default_schema
        return f"{resolved_catalog}.{resolved_schema}.{raw}"
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


JsonFieldType = Literal["string", "integer", "number", "boolean", "date", "datetime"]
_IDENTITY_SEARCH_FIELDS = ("ssn", "first_name", "last_name", "date_of_birth")


class SourceColumn(BaseModel):
    """One Unity Catalog column discovered at startup."""

    name: str = Field(min_length=1)
    type_name: str = Field(min_length=1)
    nullable: bool = True
    position: int = 0


class EffectiveField(BaseModel):
    """One source field after Unity Catalog discovery and mapping.yml overlay."""

    api_name: str = Field(min_length=1)
    column: str = Field(min_length=1)
    omit: bool = False
    json_type: JsonFieldType = "string"
    nullable: bool = True


class MappedFieldConfig(BaseModel):
    """Optional overlay for one Unity Catalog column in the public API."""

    model_config = ConfigDict(str_strip_whitespace=True)

    column: str | None = None
    omit: bool = False
    type: JsonFieldType | None = None
    nullable: bool | None = None

    @field_validator("column")
    @classmethod
    def column_is_identifier(cls, value: str | None) -> str | None:
        """Require an explicit lake column to be a SQL identifier."""
        if value is None:
            return None
        return _require_ident(value, kind="mapped column")


class MappingYaml(BaseModel):
    """Validated ``mapping.yml`` document."""

    version: Literal[1]
    sources: dict[str, dict[str, MappedFieldConfig]] = Field(default_factory=dict)

    @field_validator("sources")
    @classmethod
    def names_are_identifiers(
        cls, value: dict[str, dict[str, MappedFieldConfig]]
    ) -> dict[str, dict[str, MappedFieldConfig]]:
        """Require source and API field names to be safe identifiers."""
        for source_name, fields in value.items():
            _require_ident(source_name, kind="mapping source name")
            seen_columns: set[str] = set()
            for field_name, spec in fields.items():
                _require_ident(field_name, kind="API field")
                lake = spec.column or field_name
                if lake in seen_columns:
                    raise ValueError(
                        f"Mapping source {source_name!r} maps column "
                        f"{lake!r} more than once"
                    )
                seen_columns.add(lake)
        return value


class SourceConfig(BaseModel):
    """One reusable Unity Catalog table or view a report can query."""

    model_config = ConfigDict(str_strip_whitespace=True, populate_by_name=True)

    table: str = Field(min_length=1)
    catalog: str | None = None
    uc_schema: str | None = Field(default=None, alias="schema")
    filter: FilterConfig

    @field_validator("catalog")
    @classmethod
    def catalog_is_identifier(cls, value: str | None) -> str | None:
        """Require an optional catalog override to be a SQL identifier."""
        if value is None:
            return None
        return _require_ident(value, kind="catalog")

    @field_validator("uc_schema")
    @classmethod
    def schema_is_identifier(cls, value: str | None) -> str | None:
        """Require an optional schema override to be a SQL identifier."""
        if value is None:
            return None
        return _require_ident(value, kind="schema")


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

    mode: Literal[
        "always",
        "section_non_empty",
        "any_section_non_empty",
        "all_sections_non_empty",
        "field_present",
    ]
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
        if self.mode in ("any_section_non_empty", "all_sections_non_empty"):
            if not self.sections:
                raise ValueError(f"{self.mode} readiness requires sections")
            return self
        if not self.section or not self.field:
            raise ValueError("field_present readiness requires section and field")
        _require_ident(self.field, kind="readiness field")
        return self


class JobConfig(BaseModel):
    """One reusable Databricks job that can be started when a report is pending."""

    model_config = ConfigDict(str_strip_whitespace=True)

    job_id: int = Field(gt=0)
    parameters: dict[str, str] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def parameter_values_are_allowlisted(cls, value: dict[str, str]) -> dict[str, str]:
        """Allow only literals or request-context ``{{...}}`` placeholders."""
        for key, raw in value.items():
            if not key.strip():
                raise ValueError("Job parameter names must be non-empty")
            _validate_job_parameter_value(raw)
        return value


class OnPendingConfig(BaseModel):
    """Optional job to start when a report is not immediately ready."""

    model_config = ConfigDict(str_strip_whitespace=True)

    job: str = Field(min_length=1)

    @field_validator("job")
    @classmethod
    def job_is_identifier(cls, value: str) -> str:
        """Require the job key to be a safe identifier."""
        return _require_ident(value, kind="job name")


class ReportConfig(BaseModel):
    """One requestable report assembled from named sources."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    sections: dict[str, ReportSectionConfig] = Field(min_length=1)
    readiness: ReadinessConfig
    on_pending: OnPendingConfig | None = None

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
    """Validated ``config.yaml`` document."""

    version: Literal[1]
    application: ApplicationConfig
    databricks: DatabricksConfig
    sources: dict[str, SourceConfig]
    jobs: dict[str, JobConfig] = Field(default_factory=dict)
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

    @field_validator("jobs")
    @classmethod
    def job_names_are_identifiers(cls, value: dict[str, JobConfig]) -> dict[str, JobConfig]:
        """Require job keys to be safe identifiers."""
        for name in value:
            _require_ident(name, kind="job name")
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
        """Require identity plus consistent report/source/readiness/job references."""
        if "identity" not in self.sources:
            raise ValueError("An identity source is required for subject lookup")
        for name, source in self.sources.items():
            try:
                qualify_uc_name(
                    source.table,
                    self.databricks.default_catalog_schema,
                    source.catalog,
                    source.uc_schema,
                )
            except ValueError as exc:
                raise ValueError(f"Source {name}: {exc}") from exc
        for code, report in self.reports.items():
            for section_name, section in report.sections.items():
                if section.source not in self.sources:
                    raise ValueError(
                        f"Report {code} section {section_name} references "
                        f"unknown source {section.source!r}"
                    )
            _validate_readiness_sections(code, report)
            if report.on_pending is not None and report.on_pending.job not in self.jobs:
                raise ValueError(
                    f"Report {code} on_pending references unknown job "
                    f"{report.on_pending.job!r}"
                )
        return self


class RequestStatusValue(str, Enum):
    """Lifecycle of an official FPVR request."""

    pending = "pending"
    ready = "ready"
    failed = "failed"


def _validate_readiness_sections(code: str, report: ReportConfig) -> None:
    """Ensure readiness points at sections that exist on the report.

    Args:
        code: Report code, used in error messages.
        report: Report being validated.

    Raises:
        ValueError: If readiness section references are invalid.
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
    if readiness.mode in ("any_section_non_empty", "all_sections_non_empty"):
        unknown = [name for name in (readiness.sections or []) if name not in section_names]
        if unknown:
            raise ValueError(f"Report {code} readiness sections are not assembled: {unknown}")
        return
    if readiness.section not in section_names:
        raise ValueError(
            f"Report {code} readiness section {readiness.section!r} is not assembled"
        )


def json_type_from_uc(type_name: str) -> JsonFieldType:
    """Map a Unity Catalog ``type_name`` to a public JSON field type.

    Args:
        type_name: Databricks ``type_name`` or ``type_text``.

    Returns:
        One of the API JSON types used in generated models.
    """
    name = type_name.strip().upper().split("(", 1)[0]
    if name in {"STRING", "CHAR", "BINARY", "VARCHAR"}:
        return "string"
    if name in {"BYTE", "SHORT", "INT", "INTEGER", "LONG", "BIGINT", "SMALLINT", "TINYINT"}:
        return "integer"
    if name in {"FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"}:
        return "number"
    if name == "BOOLEAN":
        return "boolean"
    if name == "DATE":
        return "date"
    if name in {"TIMESTAMP", "TIMESTAMP_NTZ", "TIMESTAMP_LTZ"}:
        return "datetime"
    return "string"


def _validate_mapping_sources(
    sources: dict[str, SourceConfig],
    mapping: dict[str, dict[str, MappedFieldConfig]],
) -> None:
    """Reject mapping.yml sources that are not configured.

    Args:
        sources: Configured Unity Catalog sources.
        mapping: Optional API overlays keyed by source name.

    Raises:
        ValueError: If mapping.yml names a source that is not in config.yaml.
    """
    extra = sorted(set(mapping) - set(sources))
    if extra:
        raise ValueError(f"mapping.yml has unknown sources: {extra}")


def _build_effective_fields(
    source_name: str,
    columns: list[SourceColumn],
    overlay: dict[str, MappedFieldConfig],
) -> list[EffectiveField]:
    """Merge Unity Catalog columns with an optional mapping.yml overlay.

    Args:
        source_name: YAML source key, used in error messages.
        columns: Discovered lake columns in position order.
        overlay: API field overlays. Unmapped columns keep their lake names.

    Returns:
        Effective fields in Unity Catalog position order.

    Raises:
        ValueError: If a mapped column is not on the table.
    """
    uc_by_name = {column.name: column for column in columns}
    lake_to_api: dict[str, tuple[str, MappedFieldConfig]] = {}
    for api_name, spec in overlay.items():
        lake = spec.column or api_name
        if lake not in uc_by_name:
            raise ValueError(
                f"Source {source_name} mapping references unknown column {lake!r}"
            )
        lake_to_api[lake] = (api_name, spec)
    fields: list[EffectiveField] = []
    for column in columns:
        if column.name in lake_to_api:
            api_name, spec = lake_to_api[column.name]
            json_type = spec.type or json_type_from_uc(column.type_name)
            nullable = column.nullable if spec.nullable is None else spec.nullable
            omit = spec.omit
        else:
            api_name = column.name
            json_type = json_type_from_uc(column.type_name)
            nullable = column.nullable
            omit = False
        fields.append(
            EffectiveField(
                api_name=api_name,
                column=column.name,
                omit=omit,
                json_type=json_type,
                nullable=nullable,
            )
        )
    return fields


def _validate_readiness_fields(
    reports: dict[str, ReportConfig],
    effective: dict[str, list[EffectiveField]],
) -> None:
    """Require field_present readiness to use a public API field.

    Args:
        reports: Configured reports.
        effective: Merged UC + mapping fields keyed by source name.

    Raises:
        ValueError: If readiness.field is missing or omitted.
    """
    for code, report in reports.items():
        if report.readiness.mode != "field_present":
            continue
        source_name = report.sections[report.readiness.section].source
        fields = {field.api_name: field for field in effective[source_name]}
        field = report.readiness.field
        spec = fields.get(field)
        if spec is None:
            raise ValueError(
                f"Report {code} readiness field {field!r} is not an API field of "
                f"{source_name}"
            )
        if spec.omit:
            raise ValueError(
                f"Report {code} readiness field {field!r} is omitted from output"
            )


def _validate_identity_search_fields(settings: "Settings") -> None:
    """Require identity search keys to resolve to Unity Catalog columns.

    Args:
        settings: Loaded settings including discovered identity columns.

    Raises:
        ValueError: If a search field cannot be resolved.
    """
    for field in _IDENTITY_SEARCH_FIELDS:
        try:
            settings.column_for("identity", field)
        except KeyError as exc:
            raise ValueError(
                f"Identity source cannot resolve search field {field!r} from "
                "Unity Catalog columns or mapping.yml"
            ) from exc


def _validate_job_parameter_value(value: str) -> None:
    """Reject unknown ``{{...}}`` tokens in job parameter templates.

    Args:
        value: YAML parameter value.

    Raises:
        ValueError: If the value uses an unknown or malformed placeholder.
    """
    raw = value.strip()
    if "{{" not in raw and "}}" not in raw:
        return
    match = _JOB_PARAM_TOKEN.fullmatch(raw)
    if match is None or match.group(1) not in _ALLOWED_JOB_PARAM_TOKENS:
        allowed = ", ".join(sorted(_ALLOWED_JOB_PARAM_TOKENS))
        raise ValueError(
            f"Job parameter value {value!r} is not a literal or one of: {allowed}"
        )


def substitute_job_parameters(
    parameters: dict[str, str],
    *,
    request_id: str,
    report_code: str,
    subject_ssn: str,
    subject_first_name: str | None = None,
    subject_last_name: str | None = None,
    subject_date_of_birth: str | None = None,
) -> dict[str, str]:
    """Replace allowlisted placeholders with request context.

    Args:
        parameters: YAML job parameter templates.
        request_id: Official request handle.
        report_code: Configured report code.
        subject_ssn: Resolved subject SSN.
        subject_first_name: Resolved first name.
        subject_last_name: Resolved last name.
        subject_date_of_birth: Resolved date of birth as ISO date.

    Returns:
        Databricks ``job_parameters`` map with tokens substituted.
    """
    context = {
        "request_id": request_id,
        "report_code": report_code,
        "subject_ssn": subject_ssn,
        "subject_first_name": subject_first_name or "",
        "subject_last_name": subject_last_name or "",
        "subject_date_of_birth": subject_date_of_birth or "",
    }
    out: dict[str, str] = {}
    for key, raw in parameters.items():
        match = _JOB_PARAM_TOKEN.fullmatch(raw.strip())
        out[key] = context[match.group(1)] if match else raw
    return out


class Settings(BaseModel):
    """Process settings from YAML plus Unity Catalog schemas discovered at startup.

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
    jobs: dict[str, JobConfig] = Field(default_factory=dict)
    reports: dict[str, ReportConfig]
    column_mapping: dict[str, dict[str, MappedFieldConfig]]
    source_schemas: dict[str, list[SourceColumn]] = Field(default_factory=dict)
    effective_fields: dict[str, list[EffectiveField]] = Field(default_factory=dict)

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
        return qualify_uc_name(
            source.table, self.catalog_schema, source.catalog, source.uc_schema
        )

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

    def pending_job(self, report_code: str) -> JobConfig | None:
        """Return the Databricks job to start when this report is pending.

        Args:
            report_code: YAML report key.

        Returns:
            Configured job, or ``None`` if the report has no ``on_pending``.

        Raises:
            KeyError: If ``report_code`` is not configured.
        """
        report = self.reports[report_code]
        if report.on_pending is None:
            return None
        return self.jobs[report.on_pending.job]

    def source_columns(self, source_name: str) -> list[str]:
        """Return Unity Catalog column names for one source in table order.

        Args:
            source_name: YAML source key.

        Returns:
            Lake column names, including omitted join keys.

        Raises:
            KeyError: If ``source_name`` is not a known source.
        """
        return [field.column for field in self.effective_fields[source_name]]

    def omitted_fields(self, source_name: str) -> set[str]:
        """Return API field names that are selected but hidden from report JSON.

        Args:
            source_name: YAML source key.

        Returns:
            Omitted API names.
        """
        return {
            field.api_name
            for field in self.effective_fields[source_name]
            if field.omit
        }

    def column_for(self, source_name: str, field: str) -> str:
        """Return the Unity Catalog column for one API field.

        Matches the public API name first, then a case-insensitive lake column
        or API name so identity search keys resolve without a mapping overlay.

        Args:
            source_name: YAML source key.
            field: Public API field name.

        Returns:
            Lake column name.

        Raises:
            KeyError: If the source or field is unknown.
        """
        fields = self.effective_fields[source_name]
        for spec in fields:
            if spec.api_name == field:
                return spec.column
        lowered = field.lower()
        for spec in fields:
            if spec.api_name.lower() == lowered or spec.column.lower() == lowered:
                return spec.column
        raise KeyError(field)

    def api_name_for(self, source_name: str, field: str) -> str:
        """Return the public API field name for a search key or lake column.

        Args:
            source_name: YAML source key.
            field: API name or lake column name.

        Returns:
            Effective API field name after mapping overlay.

        Raises:
            KeyError: If the source or field is unknown.
        """
        lake = self.column_for(source_name, field)
        for spec in self.effective_fields[source_name]:
            if spec.column == lake:
                return spec.api_name
        raise KeyError(field)

    def identity_value(self, subject: Any, field: str) -> Any:
        """Read one identity search field from a generated identity row.

        Args:
            subject: Generated identity model instance.
            field: Canonical search key (``ssn``, ``first_name``, ...).

        Returns:
            Attribute value, or ``None`` if the generated model has no such field.
        """
        return getattr(subject, self.api_name_for("identity", field), None)

    def public_fields(self, source_name: str) -> list[str]:
        """Return API field names that are included in report JSON.

        Args:
            source_name: YAML source key.

        Returns:
            Field names in Unity Catalog order, excluding omitted fields.
        """
        return [
            field.api_name
            for field in self.effective_fields[source_name]
            if not field.omit
        ]

    def remap_row(
        self,
        source_name: str,
        uc_row: dict[str, Any],
        *,
        include_omitted: bool = False,
    ) -> dict[str, Any]:
        """Rename a lake-column dict to API field names.

        Args:
            source_name: YAML source key.
            uc_row: Values keyed by Unity Catalog column names.
            include_omitted: When true, include fields marked ``omit``.

        Returns:
            Dict keyed by API field names.
        """
        out: dict[str, Any] = {}
        for spec in self.effective_fields[source_name]:
            if spec.omit and not include_omitted:
                continue
            out[spec.api_name] = uc_row.get(spec.column)
        return out


def _discover_source_schemas(settings: Settings) -> dict[str, list[SourceColumn]]:
    """Load Unity Catalog columns for every configured source.

    Args:
        settings: YAML settings with resolved table names.

    Returns:
        Source name to discovered columns.

    Raises:
        ValueError: If auth, the tables API, or a filter column fails.
    """
    from app.core.app_auth import AppPrincipalError, get_app_sp_token
    from app.core.sql import SqlStatementError, describe_unity_catalog_table

    try:
        token = get_app_sp_token(workspace_url=settings.workspace_host)
    except AppPrincipalError as exc:
        raise ValueError(f"Cannot discover Unity Catalog schemas: {exc}") from exc
    schemas: dict[str, list[SourceColumn]] = {}
    for name, source in settings.sources.items():
        table = settings.source_table(name)
        try:
            columns = describe_unity_catalog_table(
                table, access_token=token, host=settings.workspace_host
            )
        except SqlStatementError as exc:
            raise ValueError(
                f"Cannot load Unity Catalog schema for source {name} ({table}): {exc}"
            ) from exc
        lake_names = {column.name for column in columns}
        if source.filter.column not in lake_names:
            raise ValueError(
                f"Source {name} filter column {source.filter.column!r} is not "
                f"on Unity Catalog table {table}"
            )
        schemas[name] = columns
    return schemas


@lru_cache
def get_settings() -> Settings:
    """Load and cache process-wide settings from YAML and Unity Catalog.

    Returns:
        The cached ``Settings`` instance.

    Raises:
        ValueError: If YAML is invalid or Unity Catalog discovery fails.
    """
    with _CONFIG_PATH.open(encoding="utf-8") as config_file:
        config = YamlConfig.model_validate(yaml.safe_load(config_file))

    with _MAPPING_PATH.open(encoding="utf-8") as mapping_file:
        mapping = MappingYaml.model_validate(
            yaml.safe_load(mapping_file) or {"version": 1, "sources": {}}
        )

    _validate_mapping_sources(config.sources, mapping.sources)

    injected_host = os.getenv("DATABRICKS_HOST", "").strip()
    injected_warehouse = os.getenv("DATABRICKS_WAREHOUSE_ID", "").strip()
    settings = Settings(
        app_name=config.application.name,
        environment=config.application.environment,
        workspace_host=_normalize_workspace_host(injected_host or config.databricks.host),
        warehouse_id=injected_warehouse or config.databricks.warehouse_id,
        catalog_schema=config.databricks.default_catalog_schema,
        request_log_table=config.databricks.request_log_table,
        sources=config.sources,
        jobs=config.jobs,
        reports=config.reports,
        column_mapping=mapping.sources,
    )
    schemas = _discover_source_schemas(settings)
    effective = {
        name: _build_effective_fields(name, columns, mapping.sources.get(name) or {})
        for name, columns in schemas.items()
    }
    settings = settings.model_copy(
        update={"source_schemas": schemas, "effective_fields": effective}
    )
    _validate_readiness_fields(config.reports, effective)
    _validate_identity_search_fields(settings)
    return settings

def _known_report_code(value: str) -> str:
    if value not in get_settings().reports:
        raise ValueError(f"Unknown report_code: {value}")
    return value


def _report_code_json_schema(schema: dict[str, Any]) -> None:
    """Fill the OpenAPI enum from configured reports without importing settings at type-definition time."""
    schema["enum"] = list(get_settings().reports)


ReportCode = Annotated[
    str,
    AfterValidator(_known_report_code),
    Field(min_length=1, examples=["FPVR-Application-Bundle"], json_schema_extra=_report_code_json_schema),
]