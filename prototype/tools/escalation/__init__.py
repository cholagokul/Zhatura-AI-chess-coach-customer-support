"""Zhatura AI Customer Care — Escalation Backend Package (Phase 7)."""

from .interface import EscalationBackendInterface
from .mock import MockEscalationBackend
from .real import NOT_CONNECTED_TO_REAL_BACKEND, RealEscalationBackend

__all__ = [
    "EscalationBackendInterface",
    "MockEscalationBackend",
    "RealEscalationBackend",
    "NOT_CONNECTED_TO_REAL_BACKEND",
]
