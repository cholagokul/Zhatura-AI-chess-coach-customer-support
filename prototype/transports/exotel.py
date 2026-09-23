"""Zhatura AI Customer Care — Exotel WebSocket transport (Phase 4).

Wraps one accepted Exotel Voicebot WebSocket connection:

    inbound : raw text message → validated telephony event
    outbound: PCM media / clear / mark → Exotel JSON messages

Security: this endpoint is publicly reachable through the development
tunnel. Every message is size-limited, parsed strictly, and anything
malformed is dropped with a log line — never trusted, never executed.
No credentials or secrets exist in, or pass through, this transport.

The transport owns NO conversational state; CallSession does.
"""

from __future__ import annotations

import logging

from telephony import exotel_events
from telephony.serializer import ExotelSerializer

from .base import VoiceTransport

logger = logging.getLogger(__name__)

# Hard cap on one inbound WebSocket message (media frames are tiny;
# 256 KB leaves generous headroom for anything legitimate).
MAX_MESSAGE_BYTES = 256 * 1024


class TransportClosed(Exception):
    """The WebSocket closed (hangup, network loss, or our own close)."""


class ExotelTransport(VoiceTransport):
    """One telephone call's WebSocket connection to Exotel."""

    name = "exotel"

    def __init__(self, websocket, exotel_sample_rate: int = 8000):
        """``websocket``: an accepted Starlette/FastAPI WebSocket
        (anything with async receive_text/send_text/close works —
        this also makes the transport fully testable with fakes)."""
        self._ws = websocket
        self.serializer = ExotelSerializer(
            exotel_sample_rate=exotel_sample_rate)
        self.connected = False
        self.media_received = 0
        self.media_sent = 0
        self.started = False

    # -- lifecycle -----------------------------------------------------

    async def start(self) -> None:
        self.connected = True

    async def close(self) -> None:
        """Close the WebSocket. Closing the WSS politely ends the
        Voicebot applet so the Exotel flow advances (e.g. to Hangup)."""
        if not self.connected:
            return
        self.connected = False
        try:
            await self._ws.close()
        except Exception:
            pass

    # -- inbound ---------------------------------------------------------

    async def receive(self):
        """Next parsed event, or None when the connection ends.

        Malformed/oversize/unknown messages are logged and skipped;
        a closed socket raises TransportClosed for the session to
        finalize cleanly.
        """
        while True:
            try:
                raw = await self._ws.receive_text()
            except Exception as exc:
                name = type(exc).__name__
                # Starlette raises WebSocketDisconnect on close.
                raise TransportClosed(name) from None
            if not isinstance(raw, str) or len(raw) > MAX_MESSAGE_BYTES:
                logger.warning("Dropping oversize/invalid message (%s bytes).",
                               len(raw) if isinstance(raw, str) else "?")
                continue
            try:
                event = exotel_events.parse_message(raw)
            except exotel_events.EventsError as exc:
                logger.warning("Dropping malformed Exotel message: %s", exc)
                continue
            if isinstance(event, exotel_events.UnknownEvent):
                logger.info("Ignoring unknown Exotel event: %s", event.name)
                continue
            if isinstance(event, exotel_events.StartEvent):
                self.started = True
                self.serializer.stream_sid = event.stream_sid
            return event

    # -- outbound --------------------------------------------------------

    async def _send(self, message: str) -> None:
        if not self.connected:
            raise TransportClosed("not connected")
        try:
            await self._ws.send_text(message)
        except Exception as exc:
            self.connected = False
            raise TransportClosed(type(exc).__name__) from None

    async def send_audio(self, pcm16: bytes, sample_rate: int) -> None:
        """Send PCM (mono int16, any rate) to the caller's phone."""
        for message in self.serializer.media_messages(pcm16, sample_rate):
            await self._send(message)
            self.media_sent += 1

    async def send_media_message(self, message: str) -> None:
        """Send one pre-serialized media message (used by the sink for
        streaming interleave)."""
        await self._send(message)
        self.media_sent += 1

    async def clear_audio(self) -> None:
        """Barge-in: tell Exotel to discard buffered caller-bound audio."""
        try:
            await self._send(self.serializer.clear_message())
        except TransportClosed:
            pass

    async def send_mark(self, name: str) -> None:
        await self._send(self.serializer.mark_message(name))
