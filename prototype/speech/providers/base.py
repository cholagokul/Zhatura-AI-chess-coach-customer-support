"""Zhatura AI Customer Care — Phase 7.1 Voice Provider Interface.

Defines the abstract interface for speech providers (Sarvam, ElevenLabs).
A provider owns BOTH STT and TTS for the duration of a call.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable


# Callback types matching realtime_stt.py
OnSpeechStart = Callable[[], None]
OnSpeechEnd = Callable[[], None]
OnPartial = Callable[[str], None]
OnFinal = Callable[[str, str], None]  # (text, language_code)
OnError = Callable[[str], None]
OnAudioChunk = Callable[[bytes], Awaitable[None]]


class VoiceProvider(ABC):
    """Abstract interface for a paired STT + TTS voice provider."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier ('sarvam' or 'elevenlabs')."""
        ...

    @property
    @abstractmethod
    def stt(self) -> Any:
        """The STT engine instance compatible with RealtimeSTT protocol."""
        ...

    @property
    @abstractmethod
    def tts(self) -> Any:
        """The TTS engine instance compatible with StreamingTTS protocol."""
        ...

    @abstractmethod
    async def start(self, tts_language: str = "en-IN") -> None:
        """Initialize and start both STT and TTS services."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop and clean up both STT and TTS services."""
        ...

    @abstractmethod
    def wire_stt_callbacks(
        self,
        *,
        on_speech_start: OnSpeechStart | None = None,
        on_speech_end: OnSpeechEnd | None = None,
        on_partial: OnPartial | None = None,
        on_final: OnFinal | None = None,
        on_error: OnError | None = None,
    ) -> None:
        """Wire callback hooks for incoming STT events."""
        ...

    @abstractmethod
    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Feed inbound PCM audio to the provider STT engine."""
        ...

    @abstractmethod
    async def synthesize(
        self, text: str, language_code: str, on_audio_chunk: OnAudioChunk
    ) -> None:
        """Synthesize text into audio chunks via TTS engine."""
        ...

    @abstractmethod
    def supports_tts_language(self, language_code: str) -> bool:
        """Check if provider natively supports TTS for given language."""
        ...

    @abstractmethod
    def supports_stt_language(self, language_code: str) -> bool:
        """Check if provider supports STT for given language."""
        ...

    @abstractmethod
    def map_tts_language(self, language_code: str, fallback: str = "en-IN") -> str:
        """Map requested language to a supported voice language code."""
        ...
