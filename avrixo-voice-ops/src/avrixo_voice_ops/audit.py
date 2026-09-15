"""Append-only, redacted audit trail with hash-chain integrity checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from .models import utc_now
from .redaction import TranscriptRedactor


@dataclass(slots=True, frozen=True)
class AuditRecord:
    id: str
    session_id: str
    event_type: str
    timestamp: datetime
    details: dict[str, Any]
    previous_hash: str
    record_hash: str


class AuditStore:
    """Keep immutable records and detect mutation or deletion within a process."""

    def __init__(self, redactor: TranscriptRedactor | None = None) -> None:
        self._redactor = redactor or TranscriptRedactor()
        self._records: list[AuditRecord] = []

    def append(self, session_id: str, event_type: str, details: dict[str, Any]) -> AuditRecord:
        timestamp = utc_now()
        sanitized = self._redactor.redact_value(details)
        previous_hash = self._records[-1].record_hash if self._records else "GENESIS"
        record_id = f"aud_{uuid4().hex}"
        digest = self._digest(
            record_id, session_id, event_type, timestamp, sanitized, previous_hash
        )
        record = AuditRecord(
            id=record_id,
            session_id=session_id,
            event_type=event_type,
            timestamp=timestamp,
            details=sanitized,
            previous_hash=previous_hash,
            record_hash=digest,
        )
        self._records.append(record)
        return record

    def for_session(self, session_id: str) -> tuple[AuditRecord, ...]:
        return tuple(record for record in self._records if record.session_id == session_id)

    def verify_chain(self) -> bool:
        previous_hash = "GENESIS"
        for record in self._records:
            if record.previous_hash != previous_hash:
                return False
            expected = self._digest(
                record.id,
                record.session_id,
                record.event_type,
                record.timestamp,
                record.details,
                record.previous_hash,
            )
            if expected != record.record_hash:
                return False
            previous_hash = record.record_hash
        return True

    def export_jsonl(self) -> str:
        return "\n".join(
            json.dumps(asdict(record), default=str, sort_keys=True, separators=(",", ":"))
            for record in self._records
        )

    @staticmethod
    def _digest(
        record_id: str,
        session_id: str,
        event_type: str,
        timestamp: datetime,
        details: dict[str, Any],
        previous_hash: str,
    ) -> str:
        payload = {
            "details": details,
            "event_type": event_type,
            "id": record_id,
            "previous_hash": previous_hash,
            "session_id": session_id,
            "timestamp": timestamp.isoformat(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode()).hexdigest()
