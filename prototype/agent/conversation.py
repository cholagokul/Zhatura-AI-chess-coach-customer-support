"""Zhatura AI Customer Care — multi-turn conversation memory (Phase 3).

Keeps the system prompt plus a bounded window of user/assistant turns
for the Sarvam chat model. No summarization in this phase.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "zhatura_customer_support.md"
)


class Conversation:
    """System prompt + last N turns of dialogue."""

    def __init__(
        self,
        system_prompt: str,
        max_turns: int = 20,
    ):
        if not system_prompt.strip():
            raise ValueError("System prompt must not be empty.")
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1.")
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self._turns: list[dict] = []

    @classmethod
    def from_prompt_file(
        cls, path: "str | Path | None" = None, max_turns: int = 20
    ) -> "Conversation":
        prompt_path = Path(path) if path else DEFAULT_PROMPT_PATH
        if not prompt_path.is_file():
            raise FileNotFoundError(
                f"System prompt not found: {prompt_path}"
            )
        return cls(prompt_path.read_text(encoding="utf-8"), max_turns)

    @property
    def turns(self) -> list[dict]:
        return list(self._turns)

    @property
    def turn_count(self) -> int:
        return len(self._turns) // 2

    def add_user(self, text: str) -> None:
        self._add("user", text)

    def add_assistant(self, text: str) -> None:
        self._add("assistant", text)

    def _add(self, role: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._turns.append({"role": role, "content": text})
        # Keep system prompt + at most max_turns*2 messages.
        excess = len(self._turns) - self.max_turns * 2
        if excess > 0:
            del self._turns[:excess]

    def messages(self) -> list[dict]:
        """Return messages in chat-completion format."""
        return [{"role": "system", "content": self.system_prompt}] + list(
            self._turns
        )

    def reset(self) -> None:
        self._turns.clear()
