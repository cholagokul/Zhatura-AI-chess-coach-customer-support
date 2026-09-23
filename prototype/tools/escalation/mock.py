"""Zhatura AI Customer Care — Mock Escalation Backend (Phase 7).

In-memory implementation for human escalation summaries.
"""

from __future__ import annotations

import logging

from ..models import EscalationSummary
from .interface import EscalationBackendInterface

logger = logging.getLogger("tools.escalation.mock")


class MockEscalationBackend(EscalationBackendInterface):
    """Synthetic escalation handler storing summaries in memory."""

    def __init__(self):
        self.escalations: list[EscalationSummary] = []

    async def prepare_escalation(
        self, summary: EscalationSummary
    ) -> EscalationSummary:
        self.escalations.append(summary)
        logger.info(
            "Prepared human escalation summary for role=%s, urgency=%s (issue: %s)",
            summary.caller_role,
            summary.urgency,
            summary.issue[:60],
        )
        return summary
