"""Domain services (business logic + persistence adapters)."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from app.models import Record, RecordCreate, RecordStatus, RecordUpdate


class RecordNotFoundError(LookupError):
    pass


class RecordService:
    """In-memory record store for API scaffolding / local OpenAPI testing.

    Swap the backing store for Unity Catalog / Lakebase without changing routes.
    """

    def __init__(self) -> None:
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
        with self._lock:
            record = self._items.get(record_id)
        if record is None:
            raise RecordNotFoundError(record_id)
        return record

    def create(self, body: RecordCreate, *, created_by: str | None = None) -> Record:
        record = Record.new(body, created_by=created_by)
        with self._lock:
            self._items[record.id] = record
        return record

    def update(self, record_id: str, body: RecordUpdate) -> Record:
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
        with self._lock:
            if record_id not in self._items:
                raise RecordNotFoundError(record_id)
            del self._items[record_id]


_record_service: RecordService | None = None


def get_record_service() -> RecordService:
    global _record_service
    if _record_service is None:
        _record_service = RecordService()
    return _record_service
