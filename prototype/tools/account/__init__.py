"""Zhatura AI Customer Care — Account Backend Package (Phase 7)."""

from .interface import AccountBackendInterface
from .mock import MockAccountBackend
from .real import NOT_CONNECTED_TO_REAL_BACKEND, RealAccountBackend

__all__ = [
    "AccountBackendInterface",
    "MockAccountBackend",
    "RealAccountBackend",
    "NOT_CONNECTED_TO_REAL_BACKEND",
]
