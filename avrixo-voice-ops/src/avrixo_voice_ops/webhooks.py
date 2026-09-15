"""Signed, idempotent webhook delivery with bounded retries."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from typing import cast
from urllib.parse import urlparse
from uuid import uuid4

from .idempotency import IdempotencyStatus, IdempotencyStore
from .models import WebhookDelivery
from .redaction import TranscriptRedactor

WebhookTransport = Callable[[str, Mapping[str, str], bytes], int]


class WebhookSigner:
    def __init__(self, secret: str) -> None:
        if len(secret) < 16:
            raise ValueError("webhook secret must contain at least 16 characters")
        self._secret = secret.encode()

    def sign(self, body: bytes, timestamp: int) -> str:
        signed = str(timestamp).encode() + b"." + body
        digest = hmac.new(self._secret, signed, hashlib.sha256).hexdigest()
        return f"t={timestamp},v1={digest}"

    def verify(self, body: bytes, signature: str, *, timestamp: int) -> bool:
        return hmac.compare_digest(self.sign(body, timestamp), signature)


class WebhookDispatcher:
    def __init__(
        self,
        *,
        signer: WebhookSigner,
        transport: WebhookTransport,
        idempotency: IdempotencyStore | None = None,
        redactor: TranscriptRedactor | None = None,
        max_attempts: int = 3,
    ) -> None:
        if not 1 <= max_attempts <= 3:
            raise ValueError("webhook max_attempts must be between 1 and 3")
        self.signer = signer
        self.transport = transport
        self.idempotency = idempotency or IdempotencyStore()
        self.redactor = redactor or TranscriptRedactor()
        self.max_attempts = max_attempts

    def deliver(
        self,
        *,
        url: str,
        event_type: str,
        payload: Mapping[str, object],
        idempotency_key: str,
        timestamp: int,
    ) -> WebhookDelivery:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("webhook destinations must use HTTPS")
        sanitized = self.redactor.redact_value(dict(payload))
        body = json.dumps(sanitized, sort_keys=True, separators=(",", ":")).encode()
        record, claimed = self.idempotency.claim(
            idempotency_key,
            {"url": url, "event_type": event_type, "body": body.decode()},
        )
        if not claimed:
            if record.status is IdempotencyStatus.COMPLETED:
                return cast(WebhookDelivery, record.result)
            return WebhookDelivery(
                id=f"wh_{uuid4().hex}",
                event_type=event_type,
                status_code=None,
                attempts=0,
                delivered=False,
                idempotency_key=idempotency_key,
                sanitized_error=record.sanitized_error or "delivery already in progress",
            )

        signature = self.signer.sign(body, timestamp)
        headers = {
            "content-type": "application/json",
            "x-avrixo-event": event_type,
            "x-avrixo-idempotency-key": idempotency_key,
            "x-avrixo-signature": signature,
        }
        status_code: int | None = None
        error_message: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                status_code = self.transport(url, headers, body)
                if 200 <= status_code < 300:
                    delivery = WebhookDelivery(
                        id=f"wh_{uuid4().hex}",
                        event_type=event_type,
                        status_code=status_code,
                        attempts=attempt,
                        delivered=True,
                        idempotency_key=idempotency_key,
                    )
                    self.idempotency.complete(idempotency_key, delivery)
                    return delivery
                error_message = f"endpoint returned HTTP {status_code}"
            except Exception as error:  # noqa: BLE001 - external transport boundary
                error_message = self.redactor.redact(str(error))[:240]

        delivery = WebhookDelivery(
            id=f"wh_{uuid4().hex}",
            event_type=event_type,
            status_code=status_code,
            attempts=self.max_attempts,
            delivered=False,
            idempotency_key=idempotency_key,
            sanitized_error=error_message or "delivery failed",
        )
        self.idempotency.fail(idempotency_key, delivery.sanitized_error or "delivery failed")
        return delivery
