"""Build typed source row models from Unity Catalog schemas and mapping.yml."""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, create_model

from app.core.config import EffectiveField, get_settings

_JSON_PYTHON_TYPES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "date": date,
    "datetime": datetime,
}


def _pascal_source(source_name: str) -> str:
    """Turn a source key into a Pydantic class-name prefix.

    Args:
        source_name: YAML source key (for example ``identity``).

    Returns:
        Concatenated alphanumeric segments (``Identity``).
    """
    return "".join(
        part[:1].upper() + part[1:]
        for part in source_name.replace("-", "_").split("_")
        if part
    )


def python_type_for(json_type: str) -> type:
    """Return the Python type used for one JSON field type.

    Args:
        json_type: ``string``, ``integer``, ``number``, ``boolean``, ``date``,
            or ``datetime``.

    Returns:
        Corresponding Python type; unknown names become ``str``.
    """
    return _JSON_PYTHON_TYPES.get(json_type, str)


def _model_fields(
    fields: list[EffectiveField], *, include_omitted: bool
) -> dict[str, tuple[type, object]]:
    """Build ``create_model`` field specs from effective source fields.

    Args:
        fields: Merged Unity Catalog + mapping.yml fields.
        include_omitted: When true, include fields marked ``omit``.

    Returns:
        Mapping of API field name to ``(type, default)``.
    """
    out: dict[str, tuple[type, object]] = {}
    for spec in fields:
        if spec.omit and not include_omitted:
            continue
        py_type: type = python_type_for(spec.json_type)
        if spec.nullable:
            out[spec.api_name] = (py_type | None, None)
        else:
            out[spec.api_name] = (py_type, ...)
    return out


def _create_row_model(
    name: str, fields: list[EffectiveField], *, include_omitted: bool
) -> type[BaseModel]:
    """Create one Pydantic row model.

    Args:
        name: Class name.
        fields: Effective fields for the source.
        include_omitted: When true, include omitted join keys.

    Returns:
        A model with ``extra="forbid"``.
    """
    return create_model(
        name,
        __config__=ConfigDict(extra="forbid"),
        **_model_fields(fields, include_omitted=include_omitted),
    )


@lru_cache
def ready_source_models() -> dict[str, type[BaseModel]]:
    """Return public row models for every configured source.

    Omitted mapping.yml fields (for example SSN) are excluded. Models are
    built once from the cached Unity Catalog schema.

    Returns:
        Mapping of YAML source name to its generated public row model.
    """
    settings = get_settings()
    models: dict[str, type[BaseModel]] = {}
    for source_name, fields in settings.effective_fields.items():
        prefix = _pascal_source(source_name)
        models[source_name] = _create_row_model(
            f"{prefix}SectionRow", fields, include_omitted=False
        )
    return models


@lru_cache
def identity_response_model() -> type[BaseModel]:
    """Return the identity search row model, including omitted join keys.

    Returns:
        Generated ``SubjectIdentity`` model.

    Raises:
        KeyError: If no identity source is configured.
    """
    fields = get_settings().effective_fields["identity"]
    return _create_row_model("SubjectIdentity", fields, include_omitted=True)
