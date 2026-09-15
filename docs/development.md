# Development

The Avrixo package is intentionally isolated at `avrixo-voice-ops/`. Its runtime has no external
dependency; development dependencies are locked with uv. Supported Python versions match the
audited inherited core: `>=3.10,<3.15`. CI exercises 3.10 and 3.13.

## Setup

```bash
cd avrixo-voice-ops
uv sync --extra dev
```

No `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, provider key, phone number, or SIP trunk
is needed. The deterministic providers return checked-in responses and record local calls only.
On Windows, non-UTC IANA calling windows require operating-system timezone data or the standard
Python `tzdata` package in the deployment environment; UTC works without that optional data.

## Complete validation

Run these commands from `avrixo-voice-ops/`:

```bash
uv run ruff format --check src tests scripts
uv run ruff check src tests scripts
uv run mypy src/avrixo_voice_ops tests
uv run pytest
uv run python scripts/run_evaluations.py
uv run python scripts/check_docs.py
uv run python scripts/secret_scan.py
uv run python -c "import avrixo_voice_ops"
```

The end-to-end suite covers:

- an allowlisted CRM read with deterministic STT, LLM, and TTS;
- an approval-gated CRM update rejected without a side effect; and
- a human escalation accepted into the explicit handoff state.

## Adding a tool

1. Implement a narrow handler that accepts a mapping and returns a serializable result.
2. Register a `ToolDefinition` with accurate `side_effect`, `approval_required`, and `max_attempts`
   values. Attempts must be between one and three.
3. Add its name to the relevant policy allowlist. Absence means deny.
4. For any side effect, supply an idempotency key and resolve the generated operator approval.
5. Add tests for allow, deny, rejection, duplicate delivery, error redaction, and retry exhaustion.

Do not place authorization logic in prompts or trust a model-generated approval assertion.

## Adding a provider

Implement the protocol in `providers.py` and expose only a non-secret provider label to metrics.
Use the optional `LiveKitSessionAdapter` for inherited `AgentSession` integration. Keep credentials
outside the package, ensure recording stays false unless a separate reviewed consent path is built,
and provide deterministic substitutes for every CI path.

## Upstream maintenance

Before updating the inherited base, repeat the audit in [`UPSTREAM.md`](../UPSTREAM.md), inspect
license and notice changes, and run both upstream-relevant checks and the fork-specific workflow.
Do not modify separately licensed model assets. Record substantive changes in
[`FORK_CHANGES.md`](../FORK_CHANGES.md).
