"""Thin optional boundary to the inherited LiveKit Agents runtime.

No LiveKit SDK is imported until a deployment explicitly constructs this adapter.
This keeps the Avrixo policy and test layers deterministic and credential-free.
"""

from __future__ import annotations

from typing import Any


class LiveKitSessionAdapter:
    """Construct inherited AgentSession objects with recording explicitly disabled."""

    @staticmethod
    def create_session(*, stt: Any, llm: Any, tts: Any, **options: Any) -> Any:
        if "record" in options:
            raise ValueError(
                "recording is configured when AgentSession starts, not at construction"
            )
        try:
            from livekit.agents import AgentSession  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError(
                "install the inherited livekit-agents package for runtime use"
            ) from error
        return AgentSession(stt=stt, llm=llm, tts=tts, **options)

    @staticmethod
    async def start_session(session: Any, *, agent: Any, **options: Any) -> Any:
        """Start an inherited AgentSession with recording forced off."""

        requested_recording = options.pop("record", False)
        if requested_recording is not False:
            raise ValueError("recording requires a separately reviewed consent-gated adapter")
        return await session.start(agent=agent, record=False, **options)

    @staticmethod
    async def add_sip_participant(job_context: Any, request: Any) -> Any:
        """Delegate outbound SIP creation to the inherited JobContext boundary."""

        return await job_context.add_sip_participant(request)

    @staticmethod
    async def transfer_sip_participant(job_context: Any, participant: Any, transfer_to: str) -> Any:
        """Delegate SIP transfer while leaving policy authorization outside the model."""

        return await job_context.transfer_sip_participant(participant, transfer_to)
