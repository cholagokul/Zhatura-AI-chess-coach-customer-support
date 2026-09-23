"""Zhatura AI Customer Care — Phase 1 application entry point.

Phase 1 scope ONLY: initialize configuration and logging, run health
checks (including one live Sarvam authentication test), print the
result, and exit with an appropriate status code.

No voice, telephony, STT/TTS, or agent functionality here — those are
later phases per the master plan in docs/.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Support both `python prototype/app.py` and `python -m prototype.app`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import health  # noqa: E402

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "app.log"


def setup_logging() -> None:
    """Console logging with timestamps; file log under prototype/logs/."""
    LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    # Keep third-party SDK noise (and any accidental header dumps) down.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main() -> int:
    setup_logging()
    logger = logging.getLogger("zhatura")

    print("Zhatura AI Customer Care")
    print("Phase 1 — Project Foundation")
    print()

    logger.info("Running Phase 1 health checks...")
    result = health.run_health_checks()

    print()
    print(health.format_health_report(result))
    print()

    if result.healthy:
        print("STATUS: HEALTHY")
        logger.info("Phase 1 health check passed.")
        return 0

    print("STATUS: UNHEALTHY")
    for error in result.errors:
        logger.error("%s", error)
    print()
    print("See the errors above. If SARVAM_API_KEY is missing, add it to")
    print("the project .env file (see .env.example).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
