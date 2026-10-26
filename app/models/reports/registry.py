"""Discover typed request-accepted models under ``app.models.reports``."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

from pydantic import BaseModel

_PACKAGE = "app.models.reports"
_SKIP_STEMS = frozenset({"registry", "__init__"})


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


def ready_report_models() -> dict[str, type[BaseModel]]:
    """Return ``{report_code: RequestAccepted}`` for each report module.

    The directory is resolved from this file so discovery works no matter
    which working directory the process was started from. Package files
    such as ``registry.py`` are skipped.

    Returns:
        Mapping of normalized report code to its ``*RequestAccepted`` model.
    """
    dir_path = Path(__file__).resolve().parent
    reports = [
        item.stem
        for item in dir_path.iterdir()
        if item.is_file()
        and item.suffix == ".py"
        and not item.name.startswith("_")
        and item.stem not in _SKIP_STEMS
    ]
    return {
        report_code: getattr(
            _import_report_module(report_code), f"{report_code.upper()}RequestAccepted"
        )
        for report_code in reports
    }
