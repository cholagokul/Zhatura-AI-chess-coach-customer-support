"""Zhatura AI Customer Care — Real Support Backend Placeholder (Phase 7).

Explicitly marked: NOT_CONNECTED_TO_REAL_BACKEND
Raises BackendNotConfiguredError whenever invoked.
"""

from __future__ import annotations

import logging

from ..errors import BackendNotConfiguredError
from ..models import CallbackRequest, FeedbackRecord, LeadRecord, SupportTicket
from .interface import SupportBackendInterface

logger = logging.getLogger("tools.support.real")

NOT_CONNECTED_TO_REAL_BACKEND: bool = True


class RealSupportBackend(SupportBackendInterface):
    """Placeholder adapter for real ticketing/CRM backend integration."""

    def __init__(self, endpoint_url: str = "", api_key: str = ""):
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        logger.warning(
            "RealSupportBackend initialized but marked NOT_CONNECTED_TO_REAL_BACKEND."
        )

    def _raise_not_configured(self) -> None:
        logger.error("Attempted to call real support backend which is not connected.")
        raise BackendNotConfiguredError(
            "Real support backend is not configured. NOT_CONNECTED_TO_REAL_BACKEND"
        )

    async def create_support_ticket(
        self,
        caller_id: str,
        account_id: str | None,
        issue_category: str,
        summary: str,
        conversation_summary: str,
        language: str,
        priority: str = "normal",
        idempotency_key: str | None = None,
    ) -> SupportTicket:
        self._raise_not_configured()

    async def create_callback_request(
        self,
        caller_id: str,
        account_id: str | None,
        reason: str,
        preferred_language: str,
        preferred_window: str = "earliest_available",
        idempotency_key: str | None = None,
    ) -> CallbackRequest:
        self._raise_not_configured()

    async def save_feedback(
        self,
        caller_id: str,
        account_id: str | None,
        text: str,
        category: str,
        language: str,
        idempotency_key: str | None = None,
    ) -> FeedbackRecord:
        self._raise_not_configured()

    async def create_academy_lead(
        self,
        organization_name: str,
        contact_info: str,
        student_count: int | None,
        summary: str,
        preferred_language: str,
        idempotency_key: str | None = None,
    ) -> LeadRecord:
        self._raise_not_configured()

    async def create_custom_plan_lead(
        self,
        organization_name: str,
        contact_info: str,
        student_count: int | None,
        summary: str,
        preferred_language: str,
        idempotency_key: str | None = None,
    ) -> LeadRecord:
        self._raise_not_configured()
