# Avrixo VoiceOps package

This package contains only the Avrixo-specific governance layer. It is intentionally
provider-neutral and depends only on the Python standard library. The optional
`LiveKitSessionAdapter` connects the governance lifecycle to an inherited LiveKit
`AgentSession` without changing the upstream realtime runtime.

Run the deterministic suite from this directory:

```bash
uv venv
uv pip install -e ".[dev]"
uv run pytest
```

No LiveKit Cloud account, SIP trunk, phone call, paid model provider, or credential is
required.
