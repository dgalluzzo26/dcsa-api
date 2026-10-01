"""Domain services (business logic + persistence adapters).

Services hold business rules and data access. They raise domain exceptions and
never raise ``HTTPException``; routes translate those exceptions into HTTP errors.
"""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from app.models import Record, RecordCreate, RecordStatus, RecordUpdate
from app.services.subject_identity import (
    SubjectIdentityQueryError,
    SubjectIdentityService,
    get_subject_identity_service,
)


class RecordNotFoundError(LookupError):
    """Raised when a record id does not exist in the store."""


class RecordService:
    """In-memory record store for API scaffolding and local OpenAPI testing.

    Swap the backing store for Unity Catalog or Lakebase without changing routes.
    All public methods are thread-safe.
    """

    def __init__(self) -> None:
        """Initialize an empty store."""
        self._lock = Lock()
        self._items: dict[str, Record] = {}

    def list(
        self,
        *,
        status: RecordStatus | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Record], int]:
        """List records, newest update first.

        Args:
            status: Only return records in this state.
            q: Case-insensitive substring matched against name and description.
            limit: Maximum number of records to return.
            offset: Number of matching records to skip.

        Returns:
            A tuple of the requested page of records and the total match count.
        """
        with self._lock:
            items = list(self._items.values())
        if status is not None:
            items = [r for r in items if r.status == status]
        if q:
            needle = q.strip().lower()
            items = [
                r
                for r in items
                if needle in r.name.lower() or needle in (r.description or "").lower()
            ]
        items.sort(key=lambda r: r.updated_at, reverse=True)
        total = len(items)
        return items[offset : offset + limit], total

    def get(self, record_id: str) -> Record:
        """Fetch a record by id.

        Args:
            record_id: Record identifier.

        Returns:
            The matching record.

        Raises:
            RecordNotFoundError: If no record has this id.
        """
        with self._lock:
            record = self._items.get(record_id)
        if record is None:
            raise RecordNotFoundError(record_id)
        return record

    def create(self, body: RecordCreate, *, created_by: str | None = None) -> Record:
        """Create and store a new record.

        Args:
            body: Validated create request.
            created_by: Identity of the caller creating the record.

        Returns:
            The stored record.
        """
        record = Record.new(body, created_by=created_by)
        with self._lock:
            self._items[record.id] = record
        return record

    def update(self, record_id: str, body: RecordUpdate) -> Record:
        """Apply a partial update to a record.

        Only fields explicitly set on ``body`` are changed. ``updated_at`` is
        always refreshed.

        Args:
            record_id: Record identifier.
            body: Fields to change.

        Returns:
            The updated record.

        Raises:
            RecordNotFoundError: If no record has this id.
        """
        with self._lock:
            current = self._items.get(record_id)
            if current is None:
                raise RecordNotFoundError(record_id)
            data = current.model_dump()
            patch = body.model_dump(exclude_unset=True)
            data.update(patch)
            data["updated_at"] = datetime.now(timezone.utc)
            updated = Record.model_validate(data)
            self._items[record_id] = updated
            return updated

    def delete(self, record_id: str) -> None:
        """Delete a record.

        Args:
            record_id: Record identifier.

        Raises:
            RecordNotFoundError: If no record has this id.
        """
        with self._lock:
            if record_id not in self._items:
                raise RecordNotFoundError(record_id)
            del self._items[record_id]


_record_service: RecordService | None = None


def get_record_service() -> RecordService:
    """Return the process-wide record service, creating it on first use.

    Returns:
        The shared ``RecordService``.
    """
    global _record_service
    if _record_service is None:
        _record_service = RecordService()
    return _record_service


__all__ = [
    "RecordNotFoundError",
    "RecordService",
    "SubjectIdentityQueryError",
    "SubjectIdentityService",
    "get_record_service",
    "get_subject_identity_service",
]
