"""Zhatura AI Customer Care — Escalation Backend Interface (Phase 7).

Defines the contract for synthesizing and recording human agent escalation summaries.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import EscalationSummary


class EscalationBackendInterface(ABC):
    """Abstract interface for escalation handlers."""

    @abstractmethod
    async def prepare_escalation(
        self, summary: EscalationSummary
    ) -> EscalationSummary:
        """Process and register an escalation package for human handoff."""
        ...
