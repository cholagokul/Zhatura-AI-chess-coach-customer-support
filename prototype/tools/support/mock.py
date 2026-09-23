"""Zhatura AI Customer Care — Mock Support Backend (Phase 7).

In-memory implementation of tickets, callbacks, feedback, and leads.
Guarantees write idempotency via idempotency keys.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..errors import BackendUnavailableError, ToolTimeoutError
from ..models import CallbackRequest, FeedbackRecord, LeadRecord, SupportTicket
from .interface import SupportBackendInterface

logger = logging.getLogger("tools.support.mock")


class MockSupportBackend(SupportBackendInterface):
    """Synthetic support service provider with in-memory persistence and idempotency."""

    def __init__(
        self,
        simulate_failure: bool = False,
        simulate_timeout: bool = False,
        latency_seconds: float = 0.0,
    ):
        self.simulate_failure = simulate_failure
        self.simulate_timeout = simulate_timeout
        self.latency_seconds = latency_seconds

        self.tickets: list[SupportTicket] = []
        self.callbacks: list[CallbackRequest] = []
        self.feedbacks: list[FeedbackRecord] = []
        self.leads: list[LeadRecord] = []

        self._idempotency_cache: dict[str, Any] = {}
        self._ticket_seq = 1000
        self._callback_seq = 1000
        self._feedback_seq = 1000
        self._lead_seq = 1000

    async def _simulate_wait(self) -> None:
        if self.simulate_timeout:
            await asyncio.sleep(5.0)
            raise ToolTimeoutError("Support backend operation timed out.")
        if self.simulate_failure:
            raise BackendUnavailableError("Mock support backend failure injected.")
        if self.latency_seconds > 0:
            await asyncio.sleep(self.latency_seconds)

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
        await self._simulate_wait()
        if idempotency_key and idempotency_key in self._idempotency_cache:
            logger.info("Idempotent hit for ticket key: %s", idempotency_key)
            return self._idempotency_cache[idempotency_key]

        self._ticket_seq += 1
        ticket = SupportTicket(
            ticket_id=f"TCK-{self._ticket_seq}",
            account_id=account_id,
            caller_id=caller_id,
            issue_category=issue_category,
            summary=summary,
            conversation_summary=conversation_summary,
            language=language,
            priority=priority,
            source="voice_ai",
            status="open",
        )
        self.tickets.append(ticket)
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = ticket
        logger.info("Created support ticket %s for caller %s", ticket.ticket_id, caller_id)
        return ticket

    async def create_callback_request(
        self,
        caller_id: str,
        account_id: str | None,
        reason: str,
        preferred_language: str,
        preferred_window: str = "earliest_available",
        idempotency_key: str | None = None,
    ) -> CallbackRequest:
        await self._simulate_wait()
        if idempotency_key and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]

        self._callback_seq += 1
        cb = CallbackRequest(
            request_id=f"CBK-{self._callback_seq}",
            caller_id=caller_id,
            account_id=account_id,
            reason=reason,
            preferred_language=preferred_language,
            preferred_window=preferred_window,
            status="pending",
        )
        self.callbacks.append(cb)
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = cb
        logger.info("Created callback request %s for caller %s", cb.request_id, caller_id)
        return cb

    async def save_feedback(
        self,
        caller_id: str,
        account_id: str | None,
        text: str,
        category: str,
        language: str,
        idempotency_key: str | None = None,
    ) -> FeedbackRecord:
        await self._simulate_wait()
        if idempotency_key and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]

        self._feedback_seq += 1
        fb = FeedbackRecord(
            feedback_id=f"FDB-{self._feedback_seq}",
            caller_id=caller_id,
            account_id=account_id,
            text=text,
            category=category,
            language=language,
        )
        self.feedbacks.append(fb)
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = fb
        logger.info("Saved feedback %s (category=%s)", fb.feedback_id, category)
        return fb

    async def create_academy_lead(
        self,
        organization_name: str,
        contact_info: str,
        student_count: int | None,
        summary: str,
        preferred_language: str,
        idempotency_key: str | None = None,
    ) -> LeadRecord:
        await self._simulate_wait()
        if idempotency_key and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]

        self._lead_seq += 1
        lead = LeadRecord(
            lead_id=f"LED-{self._lead_seq}",
            lead_type="academy",
            organization_name=organization_name,
            contact_info=contact_info,
            student_count=student_count,
            summary=summary,
            preferred_language=preferred_language,
        )
        self.leads.append(lead)
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = lead
        logger.info("Created academy lead %s for %s", lead.lead_id, organization_name)
        return lead

    async def create_custom_plan_lead(
        self,
        organization_name: str,
        contact_info: str,
        student_count: int | None,
        summary: str,
        preferred_language: str,
        idempotency_key: str | None = None,
    ) -> LeadRecord:
        await self._simulate_wait()
        if idempotency_key and idempotency_key in self._idempotency_cache:
            return self._idempotency_cache[idempotency_key]

        self._lead_seq += 1
        lead = LeadRecord(
            lead_id=f"LED-{self._lead_seq}",
            lead_type="custom_plan",
            organization_name=organization_name,
            contact_info=contact_info,
            student_count=student_count,
            summary=summary,
            preferred_language=preferred_language,
        )
        self.leads.append(lead)
        if idempotency_key:
            self._idempotency_cache[idempotency_key] = lead
        logger.info("Created custom plan lead %s", lead.lead_id)
        return lead
