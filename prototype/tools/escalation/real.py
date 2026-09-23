"""Zhatura AI Customer Care — Real Escalation Backend Placeholder (Phase 7).

Explicitly marked: NOT_CONNECTED_TO_REAL_BACKEND
Raises BackendNotConfiguredError whenever invoked.
"""

from __future__ import annotations

import logging

from ..errors import BackendNotConfiguredError
from ..models import EscalationSummary
from .interface import EscalationBackendInterface

logger = logging.getLogger("tools.escalation.real")

NOT_CONNECTED_TO_REAL_BACKEND: bool = True


class RealEscalationBackend(EscalationBackendInterface):
    """Placeholder adapter for telephony call transfers or CRM live escalation."""

    def __init__(self, endpoint_url: str = ""):
        self.endpoint_url = endpoint_url
        logger.warning(
            "RealEscalationBackend initialized but marked NOT_CONNECTED_TO_REAL_BACKEND."
        )

    def _raise_not_configured(self) -> None:
        logger.error("Attempted to call real escalation backend which is not connected.")
        raise BackendNotConfiguredError(
            "Real escalation backend is not configured. NOT_CONNECTED_TO_REAL_BACKEND"
        )

    async def prepare_escalation(
        self, summary: EscalationSummary
    ) -> EscalationSummary:
        self._raise_not_configured()
