# Fork changes

This file identifies work authored for Avrixo VoiceOps after the inherited LiveKit base
`7acd12aee77a2c0104fea1ca8cac7e12f99419bd`.

## Added

- `avrixo-voice-ops/src/avrixo_voice_ops/`: a standalone governed operations package with typed
  records, state transitions, contact policy, recording/transcript controls, tool governance,
  approvals, idempotency, bounded retries, escalation, audit integrity, structured outcomes,
  grounded summaries, metrics, signed webhooks, readiness checks, deterministic providers, and an
  optional LiveKit boundary.
- `avrixo-voice-ops/tests/`: deterministic policy, approval, redaction, webhook, retry, provider,
  evaluation, and end-to-end tests.
- `avrixo-voice-ops/evaluations/`: checked-in governance evaluation cases.
- `avrixo-voice-ops/scripts/`: evaluation, documentation, and offline secret checks.
- `.github/workflows/voiceops.yml`: fork-specific Python 3.10 and 3.13 validation with no secrets.
- `docs/architecture.md`, `docs/security.md`, and `docs/development.md`.
- `UPSTREAM.md` and this fork change ledger.

## Modified

- `README.md`: replaced the upstream-first landing page with a visible derivative-work notice,
  Avrixo scope, governance flow, safety boundaries, and explicit inherited-functionality section.

## Not modified

- Inherited LiveKit framework and plugin implementation.
- Root `LICENSE`, root `NOTICE`, `MODEL_LICENSE`, and embedded resource `NOTICE`.
- Separately licensed model assets, copyright notices, and Git history.

## Claims boundary

Avrixo claims only the files and changes listed above. It does not claim that LiveKit Agents was
built from scratch by Avrixo, and it makes no customer, compliance, production-volume, benchmark,
telephony-reliability, or security-certification claim.
