"""Zhatura AI Customer Care — Sarvam client factory.

Creates the official Sarvam Python SDK client (``sarvamai.SarvamAI``)
using the configured ``SARVAM_API_KEY``. Client initialization is kept
in one place so it is never duplicated across the project.

The API key is passed to the SDK but never printed, logged, or exposed.
"""

from __future__ import annotations

import logging

from sarvamai import SarvamAI

try:  # Package import (tests) and direct script execution both supported.
    from . import config as _config_module
except ImportError:  # pragma: no cover - direct `python prototype/app.py`
    import config as _config_module  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

_CLIENT_TIMEOUT_SECONDS = 15.0


class SarvamClientError(Exception):
    """Raised when the Sarvam client cannot be initialized."""


def get_sarvam_client(config: "_config_module.Config | None" = None) -> SarvamAI:
    """Return an initialized official Sarvam SDK client.

    Args:
        config: A pre-loaded :class:`config.Config`. If omitted,
            configuration is loaded from the project ``.env`` file.

    Raises:
        config.ConfigurationError: if configuration is missing.
        SarvamClientError: if the SDK client cannot be constructed.
    """
    if config is None:
        config = _config_module.load_config()

    try:
        client = SarvamAI(
            api_subscription_key=config.sarvam_api_key,
            timeout=_CLIENT_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # SDK init failure — never include the key.
        raise SarvamClientError(
            f"Sarvam client failed to initialize ({type(exc).__name__}). "
            "Check that the 'sarvamai' SDK version is supported."
        ) from None

    logger.info("Sarvam client initialized.")
    return client
