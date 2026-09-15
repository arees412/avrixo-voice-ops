# Upstream provenance

## Fork relationship

- Upstream: [livekit/agents](https://github.com/livekit/agents)
- Fork: [arees412/avrixo-voice-ops](https://github.com/arees412/avrixo-voice-ops)
- Upstream default branch at fork time: `main`
- Exact fork base: `7acd12aee77a2c0104fea1ca8cac7e12f99419bd`
- Audit date: 2026-09-15

GitHub's fork relationship and the inherited Git history are intentionally preserved. Avrixo
development is isolated on `feat/avrixo-voice-ops`; upstream code is not presented as original
Avrixo authorship.

## License and notice inventory

The audit found the following applicable repository-root and embedded notices. They remain
unchanged in this fork:

| File | Status | Scope |
| --- | --- | --- |
| [`LICENSE`](LICENSE) | Preserved | Apache License 2.0 for the repository's open-source code |
| [`NOTICE`](NOTICE) | Preserved | LiveKit copyright and Apache attribution notice |
| [`MODEL_LICENSE`](MODEL_LICENSE) | Preserved | Separate terms governing identified LiveKit model assets |
| [`livekit-agents/livekit/agents/resources/NOTICE`](livekit-agents/livekit/agents/resources/NOTICE) | Preserved | Attribution for bundled resource audio |

No separately licensed model asset is changed by the Avrixo branch. Deterministic tests use
purpose-built, standard-library providers and do not load those assets.

## Audited upstream integration points

At the base SHA, the inherited project uses Python `>=3.10,<3.15`, a uv workspace, Ruff, mypy,
pytest, and GitHub Actions. Its public architecture exposes `Agent`, `AgentSession`, `AgentServer`,
worker/job processing through `JobContext`, provider-neutral STT/LLM/TTS and realtime interfaces,
SIP participant creation/transfer, session events, and latency/token/audio metrics.

The inherited suite also includes fakes and evaluation helpers, while many provider-specific jobs
require external credentials. Avrixo's fork-specific gate is therefore isolated and deterministic:
it does not invoke provider tests, cloud inference, real phone calls, or production SIP trunks.

## Updating from upstream

1. Fetch `https://github.com/livekit/agents` as remote `upstream`.
2. Review upstream license, notice, model-license, Python, uv, AgentSession, telephony, environment,
   test, CI, and security changes before merging.
3. Merge or rebase only after the Avrixo checks pass on the candidate SHA.
4. Update this file and [`FORK_CHANGES.md`](FORK_CHANGES.md) when the audited base changes.
