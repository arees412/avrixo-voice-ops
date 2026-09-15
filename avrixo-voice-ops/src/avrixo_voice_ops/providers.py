"""Provider contracts and deterministic offline implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class SpeechToTextProvider(Protocol):
    name: str

    def transcribe(self, audio: bytes) -> str: ...


class LanguageModelProvider(Protocol):
    name: str

    def respond(self, transcript: str) -> str: ...


class TextToSpeechProvider(Protocol):
    name: str

    def synthesize(self, text: str) -> bytes: ...


class TelephonyProvider(Protocol):
    name: str

    def connect(self, session_id: str, destination: str) -> str: ...

    def transfer(self, session_id: str, destination: str) -> str: ...

    def end(self, session_id: str) -> None: ...


@dataclass(slots=True)
class DeterministicSTT:
    transcript: str
    name: str = "deterministic-stt"
    calls: int = 0

    def transcribe(self, audio: bytes) -> str:
        self.calls += 1
        if not audio:
            return ""
        return self.transcript


@dataclass(slots=True)
class DeterministicLLM:
    response: str
    name: str = "deterministic-llm"
    prompts: list[str] = field(default_factory=list)

    def respond(self, transcript: str) -> str:
        self.prompts.append(transcript)
        return self.response


@dataclass(slots=True)
class DeterministicTTS:
    name: str = "deterministic-tts"
    utterances: list[str] = field(default_factory=list)

    def synthesize(self, text: str) -> bytes:
        self.utterances.append(text)
        return f"VOICE:{text}".encode()


@dataclass(slots=True)
class DeterministicTelephony:
    name: str = "deterministic-telephony"
    events: list[tuple[str, str, str | None]] = field(default_factory=list)

    def connect(self, session_id: str, destination: str) -> str:
        self.events.append(("connect", session_id, destination))
        return f"call-{session_id}"

    def transfer(self, session_id: str, destination: str) -> str:
        self.events.append(("transfer", session_id, destination))
        return f"handoff-{session_id}"

    def end(self, session_id: str) -> None:
        self.events.append(("end", session_id, None))


@dataclass(slots=True, frozen=True)
class ProviderBundle:
    stt: SpeechToTextProvider
    llm: LanguageModelProvider
    tts: TextToSpeechProvider
    telephony: TelephonyProvider
