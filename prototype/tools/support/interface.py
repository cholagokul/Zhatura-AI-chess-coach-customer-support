"""Zhatura AI Customer Care — Support Backend Interface (Phase 7).

Defines write contracts for support tickets, callbacks, feedback, and leads.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import (
    CallbackRequest,
    FeedbackRecord,
    LeadRecord,
    SupportTicket,
)


class SupportBackendInterface(ABC):
    """Abstract interface for all support action providers."""

    @abstractmethod
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
        """Create and return a support ticket."""
        ...

    @abstractmethod
    async def create_callback_request(
        self,
        caller_id: str,
        account_id: str | None,
        reason: str,
        preferred_language: str,
        preferred_window: str = "earliest_available",
        idempotency_key: str | None = None,
    ) -> CallbackRequest:
        """Create and return a phone callback request."""
        ...

    @abstractmethod
    async def save_feedback(
        self,
        caller_id: str,
        account_id: str | None,
        text: str,
        category: str,
        language: str,
        idempotency_key: str | None = None,
    ) -> FeedbackRecord:
        """Save caller feedback or complaint."""
        ...

    @abstractmethod
    async def create_academy_lead(
        self,
        organization_name: str,
        contact_info: str,
        student_count: int | None,
        summary: str,
        preferred_language: str,
        idempotency_key: str | None = None,
    ) -> LeadRecord:
        """Record sales interest for a chess academy."""
        ...

    @abstractmethod
    async def create_custom_plan_lead(
        self,
        organization_name: str,
        contact_info: str,
        student_count: int | None,
        summary: str,
        preferred_language: str,
        idempotency_key: str | None = None,
    ) -> LeadRecord:
        """Record sales interest for a custom organization plan."""
        ...
