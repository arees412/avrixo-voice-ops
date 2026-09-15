"""In-memory idempotency primitives for deterministic adapters and tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Any


class IdempotencyStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class IdempotencyConflict(ValueError):
    """Raised when a key is reused with a different request payload."""


@dataclass(slots=True)
class IdempotencyRecord:
    key: str
    fingerprint: str
    status: IdempotencyStatus = IdempotencyStatus.PENDING
    result: Any = None
    sanitized_error: str | None = None


class IdempotencyStore:
    """Process-local store with atomic claims and stable payload fingerprints."""

    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}
        self._lock = Lock()

    @staticmethod
    def fingerprint(payload: Any) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode()).hexdigest()

    def claim(self, key: str, payload: Any) -> tuple[IdempotencyRecord, bool]:
        if not key.strip():
            raise ValueError("idempotency key cannot be empty")
        fingerprint = self.fingerprint(payload)
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise IdempotencyConflict("idempotency key reused with different payload")
                return existing, False
            record = IdempotencyRecord(key=key, fingerprint=fingerprint)
            self._records[key] = record
            return record, True

    def complete(self, key: str, result: Any) -> IdempotencyRecord:
        with self._lock:
            record = self._records[key]
            record.status = IdempotencyStatus.COMPLETED
            record.result = result
            return record

    def fail(self, key: str, sanitized_error: str) -> IdempotencyRecord:
        with self._lock:
            record = self._records[key]
            record.status = IdempotencyStatus.FAILED
            record.sanitized_error = sanitized_error
            return record

    def get(self, key: str) -> IdempotencyRecord | None:
        return self._records.get(key)
