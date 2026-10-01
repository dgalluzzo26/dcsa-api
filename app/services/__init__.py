"""Domain services (business logic + persistence adapters).

Services hold business rules and data access. They raise domain exceptions and
never raise ``HTTPException``; routes translate those exceptions into HTTP errors.
"""

from __future__ import annotations

from app.services.subject_identity import (
    SubjectIdentityQueryError,
    SubjectIdentityService,
    get_subject_identity_service,
)

__all__ = [
    "SubjectIdentityQueryError",
    "SubjectIdentityService",
    "get_subject_identity_service",
]
