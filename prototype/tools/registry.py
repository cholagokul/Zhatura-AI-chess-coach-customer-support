"""Zhatura AI Customer Care — Centralized Tool Registry (Phase 7).

Defines tool metadata, execution contracts, timeout thresholds, and confirmation requirements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    is_write_action: bool
    requires_verification: bool
    requires_confirmation: bool
    timeout_seconds: float
    category: str  # "account", "support", "escalation"


class ToolRegistry:
    """Registry of known system tools and their operational parameters."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def is_registered(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())


def create_default_registry() -> ToolRegistry:
    """Initialize the standard Phase 7 tool definitions."""
    reg = ToolRegistry()

    # Read-only lookups (timeout < 2.0s, no confirmation required)
    reg.register(ToolDefinition(
        name="account.lookup",
        description="Look up account details by verified account ID or identity",
        is_write_action=False,
        requires_verification=True,
        requires_confirmation=False,
        timeout_seconds=2.0,
        category="account",
    ))
    reg.register(ToolDefinition(
        name="student.lookup",
        description="Look up student profile by student ID",
        is_write_action=False,
        requires_verification=True,
        requires_confirmation=False,
        timeout_seconds=2.0,
        category="account",
    ))
    reg.register(ToolDefinition(
        name="session.lookup",
        description="Look up lesson/session status and schedule for a student",
        is_write_action=False,
        requires_verification=True,
        requires_confirmation=False,
        timeout_seconds=2.0,
        category="account",
    ))
    reg.register(ToolDefinition(
        name="subscription.lookup",
        description="Look up subscription tier, validity, and status for an account",
        is_write_action=False,
        requires_verification=True,
        requires_confirmation=False,
        timeout_seconds=2.0,
        category="account",
    ))

    # Write actions (timeout < 3.0s, requires confirmation where appropriate)
    reg.register(ToolDefinition(
        name="ticket.create",
        description="Create a customer support ticket for unresolved issues",
        is_write_action=True,
        requires_verification=False,  # Unverified can submit tickets; marked accordingly
        requires_confirmation=True,   # Requires caller confirmation before write
        timeout_seconds=3.0,
        category="support",
    ))
    reg.register(ToolDefinition(
        name="callback.create",
        description="Request a phone callback from human customer support",
        is_write_action=True,
        requires_verification=False,
        requires_confirmation=True,
        timeout_seconds=3.0,
        category="support",
    ))
    reg.register(ToolDefinition(
        name="feedback.create",
        description="Record caller feedback or complaint",
        is_write_action=True,
        requires_verification=False,
        requires_confirmation=False,  # Caller explicitly giving feedback can be saved immediately
        timeout_seconds=3.0,
        category="support",
    ))
    reg.register(ToolDefinition(
        name="lead.create",
        description="Register an academy or custom-plan sales lead",
        is_write_action=True,
        requires_verification=False,
        requires_confirmation=False,
        timeout_seconds=3.0,
        category="support",
    ))

    # Escalation
    reg.register(ToolDefinition(
        name="escalation.prepare",
        description="Synthesize structured escalation summary for human agent handoff",
        is_write_action=False,
        requires_verification=False,
        requires_confirmation=False,
        timeout_seconds=2.0,
        category="escalation",
    ))

    return reg
