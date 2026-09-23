"""Zhatura AI Customer Care — Phase 4 Exotel WebSocket voice service.

⚠ Makes REAL Sarvam API calls when telephone audio arrives.
Never run under pytest.

    python prototype/phase4_exotel_server.py

Exposes a Voicebot-Applet-compatible bidirectional WebSocket at
``/ws`` plus a safe ``/health`` endpoint. Each inbound WebSocket
connection becomes an independent CallSession wired to the existing
Phase 3 voice agent (STT → chat model → TTS), with telephony barge-in
via Exotel ``clear`` events.

Development exposure: ``ngrok http 8000`` → put the WSS URL into the
Exotel Voicebot applet. The Sarvam key never leaves this server.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402

logger = logging.getLogger("phase4.server")

BANNER = """
==================================================
ZHATURA AI CUSTOMER CARE — EXOTEL VOICE SERVICE
==================================================
"""


def create_app(cfg) -> FastAPI:
    """Build the FastAPI app (importable for tests without running)."""
    from sarvamai import AsyncSarvamAI
    from telephony.session import CallSession
    from transports.exotel import ExotelTransport
    from speech.providers import ProviderHealthManager, VoiceProviderManager

    app = FastAPI(title="Zhatura Exotel Voice Service", docs_url=None,
                  redoc_url=None)
    # One shared Sarvam client for the process; per-call sessions get
    # their own STT/TTS sockets, conversations and state.
    shared_client = AsyncSarvamAI(api_subscription_key=cfg.sarvam_api_key)
    app.state.active_calls = 0
    # stream_sid → CallSession, for duplicate-session defense
    app.state.sessions = {}

    cooldown = getattr(cfg, "provider_health_cooldown_seconds", 300)
    health_manager = ProviderHealthManager(default_cooldown_seconds=cooldown)
    eleven_key = (getattr(cfg, "elevenlabs_api_key", "") or "").strip()
    if not eleven_key:
        health_manager.set_unavailable("elevenlabs", "missing_api_key")
    provider_manager = VoiceProviderManager(
        cfg=cfg, sarvam_client=shared_client, health_manager=health_manager
    )
    app.state.health_manager = health_manager
    app.state.provider_manager = provider_manager

    @app.get("/health")
    async def health():
        # Safe data only — no keys, no config values.
        backend_mode = getattr(cfg, "support_backend_mode", "mock")
        primary = getattr(cfg, "voice_primary_provider", "sarvam")
        secondary = getattr(cfg, "voice_secondary_provider", "elevenlabs")
        return {
            "status": "healthy",
            "sarvam": "configured",
            "phase": 7,
            "phase_version": "7.1",
            "support_backend": backend_mode,
            "active_calls": app.state.active_calls,
            "voice_primary_provider": primary,
            "voice_secondary_provider": secondary,
            "providers": health_manager.get_status_report(),
        }

    # Support Portal routes & static assets
    support_static_dir = Path(__file__).resolve().parent / "support" / "static"
    if support_static_dir.exists():
        app.mount("/support/static", StaticFiles(directory=str(support_static_dir)), name="support_static")

    @app.get("/support", response_class=HTMLResponse)
    @app.get("/support/", response_class=HTMLResponse)
    async def support_portal():
        index_file = support_static_dir / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>Zhatura Support Center</h1>", status_code=200)

    @app.get("/support/data.json")
    async def support_data():
        data_file = support_static_dir / "data.json"
        if data_file.exists():
            return FileResponse(str(data_file), media_type="application/json")
        from support.knowledge_data import get_support_knowledge_payload
        return get_support_knowledge_payload()

    @app.websocket(cfg.exotel_ws_path)
    async def voicebot_ws(websocket: WebSocket):
        await websocket.accept()
        # Per-connection sample rate: ?sample-rate=16000 overrides
        # config (Exotel Voicebot URL may carry it).
        try:
            rate = int(websocket.query_params.get(
                "sample-rate", cfg.exotel_audio_sample_rate))
        except ValueError:
            rate = cfg.exotel_audio_sample_rate
        if rate not in (8000, 16000, 24000):
            rate = cfg.exotel_audio_sample_rate
        transport = ExotelTransport(websocket, exotel_sample_rate=rate)
        session = CallSession(cfg, transport, sarvam_client=shared_client,
                              registry=app.state.sessions,
                              provider_manager=provider_manager)
        app.state.active_calls += 1
        logger.info("New Exotel connection → session %s (rate=%d Hz). "
                    "ACTIVE CALLS: %d",
                    session.session_id, rate, app.state.active_calls)
        try:
            await session.run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[%s] Session error: %s",
                         session.session_id, type(exc).__name__)
            try:
                await session.shutdown()
            except Exception:
                pass
        finally:
            app.state.active_calls -= 1
            logger.info("[%s] Handler done. ACTIVE CALLS: %d",
                        session.session_id, app.state.active_calls)

    return app


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    try:
        cfg = config.load_config()
    except config.ConfigurationError as exc:
        print(exc)
        return 1

    print(BANNER)
    print(f"Server: READY ({cfg.exotel_ws_host}:{cfg.exotel_ws_port})")
    print(f"WebSocket: {cfg.exotel_ws_path}")
    print(f"Exotel audio: {cfg.exotel_audio_sample_rate} Hz mono linear16 "
          "(PCM, base64)")
    print("Sarvam: CONFIGURED")
    print("Voice Agent: READY (sarvam-105b-conversations)")
    print()
    print("Waiting for Exotel calls...")
    print("=" * 50)

    import uvicorn

    app = create_app(cfg)
    try:
        uvicorn.run(app, host=cfg.exotel_ws_host, port=cfg.exotel_ws_port,
                    log_level="warning")
    except KeyboardInterrupt:
        print("\nStopped by user (Ctrl+C).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
