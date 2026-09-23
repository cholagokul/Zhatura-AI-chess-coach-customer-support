"""Zhatura AI Customer Care — voice transport abstraction (Phase 4).

A VoiceTransport is the audio/IO edge of a voice session. The Phase 3
VoiceAgent and state machine are transport-agnostic; transports only
move PCM/audio events in and out.

    Local transport   → Mac microphone/speaker (Phase 3 demo)
    Exotel transport  → telephone audio over WebSocket (Phase 4)

Kept deliberately small — five async operations, nothing more.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class VoiceTransport(ABC):
    """Minimal transport interface for voice sessions."""

    name: str = "abstract"

    @abstractmethod
    async def start(self) -> None:
        """Begin receiving/sending audio for this session."""

    @abstractmethod
    async def receive(self):
        """Return the next inbound event (audio chunk or control event).

        Returns None when the transport is closed/finished.
        """

    @abstractmethod
    async def send_audio(self, pcm16: bytes, sample_rate: int) -> None:
        """Play/deliver mono int16 PCM to the human."""

    @abstractmethod
    async def clear_audio(self) -> None:
        """Barge-in: discard audio already queued/planned for playback."""

    @abstractmethod
    async def close(self) -> None:
        """Release the transport. Idempotent."""
