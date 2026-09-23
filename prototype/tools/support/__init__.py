"""Zhatura AI Customer Care — Support Backend Package (Phase 7)."""

from .interface import SupportBackendInterface
from .mock import MockSupportBackend
from .real import NOT_CONNECTED_TO_REAL_BACKEND, RealSupportBackend

__all__ = [
    "SupportBackendInterface",
    "MockSupportBackend",
    "RealSupportBackend",
    "NOT_CONNECTED_TO_REAL_BACKEND",
]
