"""Zhatura AI Customer Care — Exotel audio serialization (Phase 4).

Exotel Voicebot media streams carry base64-encoded **linear16 PCM,
mono** (verified against the ExotelFrameSerializer implementation and
Exotel Stream/Voicebot documentation). The Exotel side runs at a
configurable sample rate (8 kHz default; 16 kHz preferred here to
match the Phase 3 realtime-STT format exactly — set via the Voicebot
URL ``?sample-rate=16000`` or ``EXOTEL_AUDIO_SAMPLE_RATE``).

This module handles ONLY wire format conversion. Telephony audio never
touches the local speaker/mic, and nothing here stores audio to disk.
"""

from __future__ import annotations

import base64
import json

import numpy as np

# Outbound media chunking: 100 ms per media event.
CHUNK_MS = 100


def resample_pcm16(pcm_bytes: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Linear-interpolation resample of mono int16 PCM bytes."""
    if src_rate == dst_rate or not pcm_bytes:
        return pcm_bytes
    a = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    if len(a) == 0:
        return b""
    out_len = max(1, int(round(len(a) * dst_rate / src_rate)))
    idx = np.linspace(0, len(a) - 1, out_len)
    out = np.interp(idx, np.arange(len(a)), a)
    return np.clip(out, -32768, 32767).astype(np.int16).tobytes()


class ExotelSerializer:
    """Encode/decode Exotel Voicebot WebSocket messages for one stream."""

    def __init__(self, stream_sid: str = "", exotel_sample_rate: int = 8000):
        self.stream_sid = stream_sid
        self.exotel_sample_rate = exotel_sample_rate

    # -- inbound (Exotel → us) ----------------------------------------

    def decode_media_to_internal(self, payload_b64: bytes,
                                 internal_rate: int) -> bytes:
        """Raw Exotel-rate PCM bytes → internal STT-rate PCM bytes."""
        return resample_pcm16(payload_b64, self.exotel_sample_rate,
                              internal_rate)

    # -- outbound (us → Exotel) ----------------------------------------

    def media_messages(self, pcm_bytes: bytes, src_rate: int) -> "list[str]":
        """PCM (any rate) → list of Exotel media JSON strings.

        Resamples to the Exotel rate and splits into CHUNK_MS messages.
        """
        data = resample_pcm16(pcm_bytes, src_rate, self.exotel_sample_rate)
        chunk_bytes = int(self.exotel_sample_rate * CHUNK_MS / 1000) * 2
        if chunk_bytes <= 0:
            chunk_bytes = len(data) or 2
        messages = []
        for i in range(0, len(data), chunk_bytes):
            payload = base64.b64encode(data[i:i + chunk_bytes]).decode("ascii")
            messages.append(json.dumps({
                "event": "media",
                "stream_sid": self.stream_sid,
                "media": {"payload": payload},
            }))
        return messages

    def clear_message(self) -> str:
        """Barge-in: ask Exotel to discard buffered bot audio."""
        return json.dumps({"event": "clear", "stream_sid": self.stream_sid})

    def mark_message(self, name: str) -> str:
        """Mark the end of an utterance; Exotel echoes it when played."""
        return json.dumps({
            "event": "mark",
            "stream_sid": self.stream_sid,
            "mark": {"name": name},
        })
