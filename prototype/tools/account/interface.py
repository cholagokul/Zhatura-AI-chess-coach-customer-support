"""Zhatura AI Customer Care — Account Backend Interface (Phase 7).

Defines the contract for customer account, student, session, and subscription lookups.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import (
    AccountProfile,
    CallerIdentity,
    CoachProfile,
    ParentProfile,
    SessionInfo,
    StudentProfile,
    SubscriptionInfo,
)


class AccountBackendInterface(ABC):
    """Abstract interface for all account and student data providers."""

    @abstractmethod
    async def get_account_by_verified_identity(
        self, identity: CallerIdentity
    ) -> AccountProfile | None:
        """Fetch account record for an authenticated caller."""
        ...

    @abstractmethod
    async def get_parent_profile(self, parent_id: str) -> ParentProfile | None:
        """Fetch parent details and registered children."""
        ...

    @abstractmethod
    async def get_student_profile(self, student_id: str) -> StudentProfile | None:
        """Fetch student profile including parent and coach references."""
        ...

    @abstractmethod
    async def get_coach_profile(self, coach_id: str) -> CoachProfile | None:
        """Fetch coach profile and assigned student roster."""
        ...

    @abstractmethod
    async def get_children_for_parent(
        self, parent_id: str
    ) -> list[StudentProfile]:
        """Fetch student records registered under a given parent account."""
        ...

    @abstractmethod
    async def get_session_status(
        self, student_id: str, session_id: str | None = None
    ) -> SessionInfo | None:
        """Fetch latest or specific session details for a student."""
        ...

    @abstractmethod
    async def get_lesson_status(
        self, student_id: str, lesson_id: str | None = None
    ) -> SessionInfo | None:
        """Fetch lesson progress / status for a student."""
        ...

    @abstractmethod
    async def get_subscription_status(
        self, account_id: str
    ) -> SubscriptionInfo | None:
        """Fetch active or historical subscription tier and validity."""
        ...

    @abstractmethod
    async def get_account_status(self, account_id: str) -> dict[str, Any] | None:
        """Fetch overall account standing and active flags."""
        ...
