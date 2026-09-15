# Security

This document describes implemented controls and deployment obligations. It is not a claim of
FCA, TCPA, GDPR, HIPAA, PCI, SOC 2, or other regulatory compliance or certification.

## Trust boundaries

| Boundary | Implemented control | Deployment obligation |
| --- | --- | --- |
| Contact to session | consent, do-not-contact, direction, window, and retry policy | source lawful consent and current contact state |
| Model to tool | fail-closed allowlist and explicit decision | keep tool handlers least-privileged |
| Tool to side effect | human approval plus idempotency key | authenticate approvers and persist one-time decisions |
| Session to operator | explicit escalation state and injected destination | authorize queues and prevent destination injection |
| Transcript to storage | credential/card/code redaction and optional email/phone masking | configure regional retention and access controls |
| Session to webhook | HTTPS, HMAC-SHA256, canonical JSON, idempotency, three-attempt ceiling | rotate secrets and reject stale signatures |
| Avrixo to LiveKit | lazy adapter and explicit `record=False` | provide scoped LiveKit/provider credentials at runtime |

## Recording and transcripts

Recording defaults to disabled in both `ContactPolicyProfile` and `LiveKitSessionAdapter`. A policy
cannot enable recording unless `recording_consent_confirmed` is also true, and the reference
LiveKit adapter still rejects `record=True`. A real recording implementation is intentionally left
as a deployment-specific, consent-gated extension.

Transcripts can be disabled. When enabled, secrets, bearer tokens, authentication codes, card-like
numbers, and configured email/phone data are redacted before turns enter the audit trail. Retention
is opt-in; the controller clears in-memory turns after summary generation when retention is off.
Redaction reduces exposure but is not a substitute for encryption, access control, retention
enforcement, or manual review of new data classes.

## Tool and approval policy

- Unknown and non-allowlisted tools return `deny`.
- Restricted tools return `deny` even if also proposed by a model.
- Every side effect returns `requires_approval` and requires an idempotency key.
- An approval is bound to one session and invocation. Scope mismatches fail closed.
- Rejected approvals do not execute; approval records are single-decision.
- Tool and webhook attempts are capped at three; no unbounded retry loop exists.
- Errors are redacted and truncated before audit or return.

The reference stores are in-memory. Production use requires atomic, durable idempotency and
approval stores so multiple workers cannot race or replay side effects.

## Webhook verification

Receivers should parse `x-avrixo-signature`, reconstruct `timestamp + "." + raw_body`, verify the
HMAC-SHA256 digest using constant-time comparison, enforce an application-defined timestamp
tolerance, and atomically deduplicate `x-avrixo-idempotency-key`. The example signer implements
the digest and constant-time comparison; timestamp freshness remains the receiver's responsibility.

## Secrets and environment

No credential is required by tests or evaluation cases. Never commit `.env`, LiveKit keys, provider
tokens, SIP credentials, phone numbers, customer transcripts, or webhook secrets. Deployments
should inject secrets from a managed secret store, scope them per environment, rotate after any
suspected exposure, and keep raw values out of logs and metrics.

The fork-specific CI runs a small offline pattern scan over Avrixo-authored files. It is a guardrail,
not proof that a secret is absent. Use platform secret scanning and dependency/security review in
production.

## Explicit non-goals

- No MFA, OTP, CAPTCHA, or security-control bypass.
- No real phone call, paid model invocation, or production SIP trunk in CI.
- No claim that in-memory stores are production-ready.
- No modification or redistribution claim beyond the preserved repository licenses and notices.

See [architecture](architecture.md) and [development](development.md).
