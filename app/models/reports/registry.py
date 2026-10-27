"""Discover typed request-accepted models under ``app.models.reports``."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from types import ModuleType

from pydantic import BaseModel

from app.core.config import get_settings

_PACKAGE = "app.models.reports"
_SKIP_STEMS = frozenset({"registry", "__init__"})
logger = logging.getLogger("dcsa")


def _report_module_stems() -> list[str]:
    """Return file stems for report modules next to this registry.

    Package files such as ``registry.py`` and ``_``-prefixed modules are skipped.

    Returns:
        Report codes derived from ``*.py`` file stems.
    """
    dir_path = Path(__file__).resolve().parent
    return [
        item.stem
        for item in dir_path.iterdir()
        if item.is_file()
        and item.suffix == ".py"
        and not item.name.startswith("_")
        and item.stem not in _SKIP_STEMS
    ]


def _expected_request_accepted_name(report_code: str) -> str:
    """Return the ``*RequestAccepted`` class name for a report code.

    Args:
        report_code: Normalized report code / file stem (for example ``fpvr1``).

    Returns:
        Expected class name, such as ``FPVR1RequestAccepted``.
    """
    return f"{report_code.upper()}RequestAccepted"


def _import_report_module(report_code: str) -> ModuleType:
    """Import the report envelope module for a normalized report code.

    Args:
        report_code: File stem / HTTP path segment (for example ``fpvr1``).

    Returns:
        The imported module.

    Raises:
        ValueError: If no matching module exists.
    """
    try:
        return importlib.import_module(f"{_PACKAGE}.{report_code.upper()}")
    except ModuleNotFoundError:
        try:
            return importlib.import_module(f"{_PACKAGE}.{report_code.lower()}")
        except ModuleNotFoundError as e:
            raise ValueError(f"Unknown report code: {report_code}") from e


def discover_report_models() -> dict[str, type[BaseModel]]:
    """Return ``{report_code: RequestAccepted}`` for every report module on disk.

    The directory is resolved from this file so discovery works no matter
    which working directory the process was started from. Package files
    such as ``registry.py`` are skipped. Config is not consulted.

    Returns:
        Mapping of report code (file stem) to its ``*RequestAccepted`` model.
    """
    return {
        report_code: getattr(
            _import_report_module(report_code),
            _expected_request_accepted_name(report_code),
        )
        for report_code in _report_module_stems()
    }


def ready_report_models() -> dict[str, type[BaseModel]]:
    """Return ``{report_code: RequestAccepted}`` for reports enabled in settings.

    Returns:
        Mapping of enabled report code to its ``*RequestAccepted`` model.
    """
    enabled = get_settings().reports
    return {
        report_code: model
        for report_code, model in discover_report_models().items()
        if report_code in enabled
    }


def warn_report_model_mismatches() -> None:
    """Warn when config report codes and on-disk report modules diverge.

    Config-only reports name the missing ``*RequestAccepted`` class. Disk-only
    modules are listed as extra files not present in ``config.yaml``.
    """
    configured = set(get_settings().reports)
    on_disk = set(_report_module_stems())
    missing_modules = sorted(configured - on_disk)
    extra_modules = sorted(on_disk - configured)
    if missing_modules:
        missing_models = [
            f"{code} ({_expected_request_accepted_name(code)} in {_PACKAGE}.{code})"
            for code in missing_modules
        ]
        logger.warning(
            "Reports in config.yaml have no module under %s: %s",
            _PACKAGE,
            ", ".join(missing_models),
        )
    if extra_modules:
        logger.warning(
            "Report modules under %s are not listed in config.yaml: %s",
            _PACKAGE,
            ", ".join(extra_modules),
        )
