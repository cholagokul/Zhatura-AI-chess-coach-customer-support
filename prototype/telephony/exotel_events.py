"""Zhatura AI Customer Care — Exotel Voicebot WebSocket events (Phase 4).

Parses and validates Exotel Voicebot Applet WebSocket messages into
typed events. The public endpoint is reachable through a development
tunnel, so every inbound message is treated as untrusted:

- invalid JSON → EventsError (caller logs + ignores)
- over-size messages are rejected by the transport before parsing
- unknown event types → UnknownEvent (logged, ignored)
- custom parameters are data only — never executed, never trusted

Protocol reference: Exotel "Stream and Voicebot Applet" docs
(events: connected / start / media / dtmf / mark / clear / stop;
media payloads are base64-encoded linear PCM, mono).
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, field


class EventsError(Exception):
    """Malformed or unusable Exotel message (safe message only)."""


@dataclass(frozen=True)
class ConnectedEvent:
    event: str = "connected"


@dataclass(frozen=True)
class StartEvent:
    stream_sid: str
    call_sid: str = ""
    account_sid_present: bool = False
    # Custom parameters from the Exotel flow (Voicebot passthrough).
    # Keys only are logged; values are data, never trusted as code.
    custom_param_keys: tuple = ()
    custom_params: dict = field(default_factory=dict)
    event: str = "start"


@dataclass(frozen=True)
class MediaEvent:
    payload: bytes  # decoded raw linear16 PCM, mono, at the Exotel rate
    sequence: str = ""
    chunk: str = ""
    timestamp: str = ""
    event: str = "media"


@dataclass(frozen=True)
class DtmfEvent:
    digit: str  # single sanitized digit/character
    event: str = "dtmf"


@dataclass(frozen=True)
class MarkEvent:
    name: str
    event: str = "mark"


@dataclass(frozen=True)
class ClearEvent:
    event: str = "clear"


@dataclass(frozen=True)
class StopEvent:
    call_sid: str = ""
    event: str = "stop"


@dataclass(frozen=True)
class UnknownEvent:
    name: str


_MAX_STR = 256          # generous bound for identifier fields
_MAX_DIGITS = 2         # DTMF is one key; allow tiny slack, then drop


def _short(value, field_name: str) -> str:
    if not isinstance(value, str):
        raise EventsError(f"{field_name} must be a string")
    return value[:_MAX_STR]


def parse_message(raw: "str | bytes"):
    """Parse one raw WebSocket text message into a typed event.

    Raises EventsError for anything malformed. Never raises for
    merely *unknown* events — those become UnknownEvent.
    """
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8", errors="replace")
        except Exception:
            raise EventsError("message is not decodable text") from None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise EventsError("invalid JSON") from None
    if not isinstance(data, dict):
        raise EventsError("message is not a JSON object")
    event = data.get("event")
    if not isinstance(event, str):
        raise EventsError("missing 'event' field")

    if event == "connected":
        return ConnectedEvent()

    if event == "start":
        start = data.get("start")
        nested = start if isinstance(start, dict) else data
        stream_sid = nested.get("stream_sid") or data.get("stream_sid") or ""
        if not stream_sid:
            raise EventsError("start event missing stream_sid")
        call_sid = nested.get("call_sid") or data.get("call_sid") or ""
        custom = nested.get("custom_parameters")
        if not isinstance(custom, dict):
            custom = {}
        # Values are truncated; keys retained for diagnostics.
        safe_custom = {str(k)[:64]: _safe_custom_value(v)
                       for k, v in list(custom.items())[:32]}
        return StartEvent(
            stream_sid=_short(stream_sid, "stream_sid"),
            call_sid=_short(call_sid, "call_sid") if call_sid else "",
            account_sid_present=bool(nested.get("account_sid")),
            custom_param_keys=tuple(sorted(safe_custom)),
            custom_params=safe_custom,
        )

    if event == "media":
        media = data.get("media")
        if not isinstance(media, dict):
            raise EventsError("media event missing 'media' object")
        payload_b64 = media.get("payload")
        if not isinstance(payload_b64, str):
            raise EventsError("media event missing base64 payload")
        try:
            payload = base64.b64decode(payload_b64, validate=True)
        except (binascii.Error, ValueError):
            raise EventsError("media payload is not valid base64") from None
        return MediaEvent(
            payload=payload,
            sequence=str(media.get("sequence_number", ""))[:16],
            chunk=str(media.get("chunk", ""))[:16],
            timestamp=str(media.get("timestamp", ""))[:16],
        )

    if event == "dtmf":
        dtmf = data.get("dtmf")
        digit = dtmf.get("digit") if isinstance(dtmf, dict) else None
        if not isinstance(digit, str) or not digit:
            raise EventsError("dtmf event missing digit")
        return DtmfEvent(digit=digit[:_MAX_DIGITS])

    if event == "mark":
        mark = data.get("mark")
        name = mark.get("name") if isinstance(mark, dict) else None
        if not isinstance(name, str) or not name:
            raise EventsError("mark event missing name")
        return MarkEvent(name=_short(name, "mark name"))

    if event == "clear":
        return ClearEvent()

    if event == "stop":
        call_sid = data.get("call_sid") or ""
        return StopEvent(
            call_sid=_short(call_sid, "call_sid") if call_sid else "")

    return UnknownEvent(name=event[:64])


def _safe_custom_value(value) -> str:
    """Custom parameter values become short strings; never dicts of code."""
    text = str(value)
    return text[:_MAX_STR]
