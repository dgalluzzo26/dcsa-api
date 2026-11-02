"""Typed FPVR-6 response envelope using agency DTOs, not table columns."""

from app.models.dto.fpvr6 import FPVR6ReportData, IdentityDto
from app.models.fpvr import OfficialReport, OfficialRequestAccepted
from app.models.reports.registry import register_report


class FPVR6Report(OfficialReport[FPVR6ReportData]):
    """FPVR-6 report. ``subject`` uses IdentityDto, not warehouse column names."""

    subject: IdentityDto


@register_report("FPVR-6")
class FPVR6RequestAccepted(OfficialRequestAccepted[FPVR6ReportData]):
    """FPVR-6 request envelope. ``report`` is set when status is ready."""

    report: FPVR6Report | None = None
