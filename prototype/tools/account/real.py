"""Zhatura AI Customer Care — Real Account Backend Placeholder (Phase 7).

Explicitly marked: NOT_CONNECTED_TO_REAL_BACKEND
Raises BackendNotConfiguredError whenever invoked.
"""

from __future__ import annotations

import logging
from typing import Any

from ..errors import BackendNotConfiguredError
from ..models import (
    AccountProfile,
    CallerIdentity,
    CoachProfile,
    ParentProfile,
    SessionInfo,
    StudentProfile,
    SubscriptionInfo,
)
from .interface import AccountBackendInterface

logger = logging.getLogger("tools.account.real")

NOT_CONNECTED_TO_REAL_BACKEND: bool = True


class RealAccountBackend(AccountBackendInterface):
    """Placeholder adapter for future real Zhatura account service integration."""

    def __init__(self, endpoint_url: str = "", api_token: str = ""):
        self.endpoint_url = endpoint_url
        self.api_token = api_token
        logger.warning(
            "RealAccountBackend initialized but marked NOT_CONNECTED_TO_REAL_BACKEND."
        )

    def _raise_not_configured(self) -> None:
        logger.error("Attempted to call real account backend which is not connected.")
        raise BackendNotConfiguredError(
            "Real account backend is not configured. NOT_CONNECTED_TO_REAL_BACKEND"
        )

    async def get_account_by_verified_identity(
        self, identity: CallerIdentity
    ) -> AccountProfile | None:
        self._raise_not_configured()

    async def get_parent_profile(self, parent_id: str) -> ParentProfile | None:
        self._raise_not_configured()

    async def get_student_profile(self, student_id: str) -> StudentProfile | None:
        self._raise_not_configured()

    async def get_coach_profile(self, coach_id: str) -> CoachProfile | None:
        self._raise_not_configured()

    async def get_children_for_parent(
        self, parent_id: str
    ) -> list[StudentProfile]:
        self._raise_not_configured()

    async def get_session_status(
        self, student_id: str, session_id: str | None = None
    ) -> SessionInfo | None:
        self._raise_not_configured()

    async def get_lesson_status(
        self, student_id: str, lesson_id: str | None = None
    ) -> SessionInfo | None:
        self._raise_not_configured()

    async def get_subscription_status(
        self, account_id: str
    ) -> SubscriptionInfo | None:
        self._raise_not_configured()

    async def get_account_status(self, account_id: str) -> dict[str, Any] | None:
        self._raise_not_configured()
