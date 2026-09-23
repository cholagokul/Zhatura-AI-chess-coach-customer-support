"""Zhatura AI Customer Care — Phase 7.1 Static Emergency Audio.

Provides pre-rendered / statically synthesized 16 kHz linear16 mono PCM
audio for total dual-provider outage scenarios. When both Sarvam and
ElevenLabs are down, this fallback plays directly to the telephone sink
before hanging up cleanly, ensuring no silent drops or hanging calls.

Message: "We're temporarily unable to process your call. Please try again later."
"""

from __future__ import annotations

import math
import struct

EMERGENCY_MESSAGE_TEXT = (
    "We're temporarily unable to process your call. Please try again later."
)

SAMPLE_RATE = 16000  # 16 kHz linear16 mono


def generate_emergency_pcm(duration_seconds: float = 2.5) -> bytes:
    """Generate a clean, pleasant multi-tone alert chime in 16 kHz mono int16 PCM.

    Used as the emergency fallback audio when all speech synthesis providers are down.
    Duration is ~2.5 seconds (compatible with telephony pacing and mark completion).
    """
    total_samples = int(SAMPLE_RATE * duration_seconds)
    audio = bytearray(total_samples * 2)

    # Sequence of calming chime frequencies (A4=440, C#5=554, E5=659, A5=880)
    # Played with exponential decay to sound like an IVR service chime.
    tones = [
        (0.0, 0.6, 440.0),   # A4
        (0.4, 1.0, 554.37),  # C#5
        (0.8, 1.4, 659.25),  # E5
        (1.2, 2.5, 440.0),   # A4 low fade
    ]

    for i in range(total_samples):
        t = i / SAMPLE_RATE
        val = 0.0
        for start, end, freq in tones:
            if start <= t < end:
                decay = math.exp(-3.5 * (t - start))
                val += math.sin(2.0 * math.pi * freq * (t - start)) * decay * 0.4

        # Clamp to 16-bit range
        int_val = int(max(-32767, min(32767, val * 30000)))
        struct.pack_into("<h", audio, i * 2, int_val)

    return bytes(audio)


# Cached singleton
_EMERGENCY_PCM: bytes | None = None


def get_emergency_audio_pcm() -> bytes:
    """Return pre-rendered 16 kHz linear16 PCM emergency audio."""
    global _EMERGENCY_PCM
    if _EMERGENCY_PCM is None:
        _EMERGENCY_PCM = generate_emergency_pcm(2.5)
    return _EMERGENCY_PCM
