"""Zhatura AI Customer Care — Phase 1 health checks.

Runs local checks (environment, configuration, client initialization)
and one minimal live Sarvam API request to verify that the configured
API subscription key actually authenticates.

No secret values are ever printed or logged.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field

try:
    from . import config as _config_module
    from .sarvam_client import SarvamClientError, get_sarvam_client
except ImportError:  # pragma: no cover - direct `python prototype/app.py`
    import config as _config_module  # type: ignore[no-redef]
    from sarvam_client import (  # type: ignore[no-redef]
        SarvamClientError,
        get_sarvam_client,
    )

logger = logging.getLogger(__name__)

MIN_PYTHON = (3, 9)


@dataclass
class HealthResult:
    """Structured result of the Phase 1 health checks."""

    python_ok: bool = False
    python_version: str = ""
    env_file_found: bool = False
    configuration: str = "FAIL"  # PASS / FAIL
    sarvam_key: str = "MISSING"  # CONFIGURED / MISSING
    sarvam_client: str = "FAIL"  # PASS / FAIL / SKIPPED
    sarvam_api: str = "FAILED"  # CONNECTED / FAILED / SKIPPED
    sarvam_api_reason: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return (
            self.python_ok
            and self.configuration == "PASS"
            and self.sarvam_key == "CONFIGURED"
            and self.sarvam_client == "PASS"
            and self.sarvam_api == "CONNECTED"
        )


def _check_python(result: HealthResult) -> None:
    result.python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    result.python_ok = sys.version_info >= MIN_PYTHON
    if not result.python_ok:
        result.errors.append(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required "
            f"(found {result.python_version})."
        )


def check_sarvam_api(client) -> tuple[bool, str]:
    """Make one minimal live Sarvam API call to verify authentication.

    Uses a tiny chat completion (max_tokens=1) to keep cost negligible.

    Returns:
        (success, reason). ``reason`` is empty on success and otherwise a
        safe human-readable explanation that never contains secrets.
    """
    try:
        response = client.chat.completions(
            model="sarvam-105b",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
    except Exception as exc:
        return False, _classify_api_error(exc)

    if response is None:
        return False, "empty response from Sarvam API"
    logger.info("Sarvam API connectivity check succeeded.")
    return True, ""


def _classify_api_error(exc: Exception) -> str:
    """Map a Sarvam SDK exception to a safe, readable reason."""
    status = getattr(exc, "status_code", None)

    if status in (401, 403):
        return "authentication failure — SARVAM_API_KEY is invalid or expired"
    if status == 429:
        return "rate limit reached — try again shortly"
    if status is not None and 500 <= status < 600:
        return f"Sarvam service error (HTTP {status}) — try again later"

    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "api" in name and ("403" in message or "401" in message or "forbidden" in message):
        return "authentication failure — SARVAM_API_KEY is invalid or expired"
    if any(
        word in name or word in message
        for word in ("connect", "timeout", "network", "unreachable")
    ):
        return "network/connectivity failure — could not reach the Sarvam API"
    return f"unexpected error ({type(exc).__name__})"


def run_health_checks() -> HealthResult:
    """Run all Phase 1 health checks and return a structured result."""
    result = HealthResult()

    _check_python(result)
    logger.info("Python %s (minimum %s.%s).", result.python_version, *MIN_PYTHON)

    result.env_file_found = _config_module.ENV_FILE.is_file()

    # Configuration + client
    try:
        cfg = _config_module.load_config()
    except _config_module.ConfigurationError as exc:
        result.configuration = "FAIL"
        result.sarvam_key = "MISSING"
        result.errors.append(str(exc))
        logger.error("Configuration check failed.")
        result.sarvam_client = "SKIPPED"
        result.sarvam_api = "SKIPPED"
        result.sarvam_api_reason = "configuration incomplete"
        return result

    result.configuration = "PASS"
    result.sarvam_key = "CONFIGURED"
    logger.info("Configuration loaded (SARVAM_API_KEY detected in .env).")

    try:
        client = get_sarvam_client(cfg)
    except (_config_module.ConfigurationError, SarvamClientError) as exc:
        result.sarvam_client = "FAIL"
        result.sarvam_api = "SKIPPED"
        result.errors.append(str(exc))
        result.sarvam_api_reason = "client initialization failed"
        return result

    result.sarvam_client = "PASS"

    # Live API check (one minimal request)
    ok, reason = check_sarvam_api(client)
    result.sarvam_api = "CONNECTED" if ok else "FAILED"
    result.sarvam_api_reason = reason
    if not ok:
        result.errors.append(f"Sarvam API check failed: {reason}")

    return result


def format_health_report(result: HealthResult) -> str:
    """Render the health result for console output. No secrets included."""
    env_status = "FOUND" if result.env_file_found else "NOT FOUND (.env missing)"
    lines = [
        "=" * 50,
        "ZHATURA AI CUSTOMER CARE — HEALTH CHECK",
        "=" * 50,
        "",
        f"Python Version:     {result.python_version} "
        f"({'PASS' if result.python_ok else 'FAIL — 3.9+ required'})",
        f".env File:          {env_status}",
        f"Configuration:      {result.configuration}",
        f"Sarvam API Key:     {result.sarvam_key}",
        f"Sarvam Client:      {result.sarvam_client}",
        f"Sarvam API:         {result.sarvam_api}",
    ]
    if result.sarvam_api_reason:
        lines.append(f"Reason:             {result.sarvam_api_reason}")
    lines += [
        "",
        f"Overall Status: {'HEALTHY' if result.healthy else 'UNHEALTHY'}",
        "=" * 50,
    ]
    return "\n".join(lines)
