"""Zhatura AI Customer Care — conversation state machine (Phase 3).

Explicit states for the live voice agent. Transitions are validated
and logged so the demo never drifts into an uncontrolled set of
booleans.
"""

from __future__ import annotations

import logging
from enum import Enum, auto

logger = logging.getLogger(__name__)


class AgentState(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()
    INTERRUPTED = auto()
    STOPPING = auto()
    ERROR = auto()


_ALLOWED = {
    AgentState.IDLE: {AgentState.LISTENING, AgentState.SPEAKING,
                      AgentState.STOPPING, AgentState.ERROR},
    AgentState.LISTENING: {AgentState.PROCESSING, AgentState.SPEAKING,
                           AgentState.STOPPING, AgentState.ERROR},
    AgentState.PROCESSING: {AgentState.SPEAKING, AgentState.LISTENING,
                            AgentState.INTERRUPTED, AgentState.STOPPING,
                            AgentState.ERROR},
    AgentState.SPEAKING: {AgentState.LISTENING, AgentState.INTERRUPTED,
                          AgentState.STOPPING, AgentState.ERROR},
    AgentState.INTERRUPTED: {AgentState.LISTENING, AgentState.PROCESSING,
                             AgentState.STOPPING, AgentState.ERROR},
    AgentState.ERROR: {AgentState.STOPPING, AgentState.LISTENING},
    AgentState.STOPPING: set(),
}


class InvalidTransition(Exception):
    """Raised when a state transition is not allowed."""


class AgentStateMachine:
    """Validated, logged state machine for the voice agent."""

    def __init__(self, initial: AgentState = AgentState.IDLE):
        self._state = initial

    @property
    def state(self) -> AgentState:
        return self._state

    def transition(self, new_state: AgentState) -> AgentState:
        """Move to ``new_state``; raise InvalidTransition if not allowed."""
        if new_state is self._state:
            return self._state
        if new_state not in _ALLOWED[self._state]:
            raise InvalidTransition(
                f"{self._state.name} → {new_state.name} is not allowed."
            )
        logger.info("STATE: %s → %s", self._state.name, new_state.name)
        self._state = new_state
        return self._state
