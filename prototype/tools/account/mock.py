"""Zhatura AI Customer Care — Mock Account Backend (Phase 7).

In-memory mock adapter loaded from synthetic account fixtures.
Does NOT touch any real production data or external servers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from ..errors import BackendUnavailableError, ToolTimeoutError
from ..models import (
    AccountProfile,
    CallerIdentity,
    CallerRole,
    CoachProfile,
    ParentProfile,
    SessionInfo,
    StudentProfile,
    SubscriptionInfo,
)
from .interface import AccountBackendInterface

logger = logging.getLogger("tools.account.mock")

DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "accounts.json"
)


class MockAccountBackend(AccountBackendInterface):
    """Synthetic account provider for testing and development."""

    def __init__(
        self,
        fixture_path: str | Path | None = None,
        simulate_failure: bool = False,
        simulate_timeout: bool = False,
        latency_seconds: float = 0.0,
    ):
        self.fixture_path = Path(fixture_path or DEFAULT_FIXTURE_PATH)
        self.simulate_failure = simulate_failure
        self.simulate_timeout = simulate_timeout
        self.latency_seconds = latency_seconds
        self._accounts: dict[str, dict] = {}
        self._students: dict[str, dict] = {}
        self._sessions: dict[str, list[dict]] = {}
        self._subscriptions: dict[str, dict] = {}
        self._load_fixtures()

    def _load_fixtures(self) -> None:
        if not self.fixture_path.is_file():
            logger.warning("Mock account fixture not found at %s", self.fixture_path)
            return

        try:
            with open(self.fixture_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for acc in data.get("accounts", []):
                self._accounts[acc["account_id"]] = acc

            for stu in data.get("students", []):
                self._students[stu["student_id"]] = stu

            for ses in data.get("sessions", []):
                student_id = ses["student_id"]
                if student_id not in self._sessions:
                    self._sessions[student_id] = []
                self._sessions[student_id].append(ses)

            for sub in data.get("subscriptions", []):
                self._subscriptions[sub["account_id"]] = sub

            logger.info(
                "MockAccountBackend loaded (%d accounts, %d students, %d sessions, %d subscriptions).",
                len(self._accounts),
                len(self._students),
                sum(len(s) for s in self._sessions.values()),
                len(self._subscriptions),
            )
        except Exception:
            logger.exception("Failed to load mock accounts fixture.")

    async def _simulate_wait(self) -> None:
        if self.simulate_timeout:
            await asyncio.sleep(5.0)
            raise ToolTimeoutError("Backend lookup timed out.")
        if self.simulate_failure:
            raise BackendUnavailableError("Mock backend failure injected.")
        if self.latency_seconds > 0:
            await asyncio.sleep(self.latency_seconds)

    async def get_account_by_verified_identity(
        self, identity: CallerIdentity
    ) -> AccountProfile | None:
        await self._simulate_wait()
        account_id = identity.account_id
        if not account_id:
            # Match by phone or student_id if account_id is not yet set
            for acc in self._accounts.values():
                if identity.phone and acc.get("phone") == identity.phone:
                    account_id = acc["account_id"]
                    break
        if not account_id or account_id not in self._accounts:
            return None

        data = self._accounts[account_id]
        return AccountProfile(
            account_id=data["account_id"],
            role=CallerRole(data.get("role", "unknown")),
            name=data.get("name", ""),
            status=data.get("status", "active"),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            created_at=data.get("created_at", ""),
            children=data.get("children", []),
            assigned_students=data.get("assigned_students", []),
            org_id=data.get("org_id"),
            org_name=data.get("org_name"),
        )

    async def get_parent_profile(self, parent_id: str) -> ParentProfile | None:
        await self._simulate_wait()
        data = self._accounts.get(parent_id)
        if not data or data.get("role") != "parent":
            return None
        return ParentProfile(
            account_id=data["account_id"],
            name=data.get("name", ""),
            children=data.get("children", []),
        )

    async def get_student_profile(self, student_id: str) -> StudentProfile | None:
        await self._simulate_wait()
        data = self._students.get(student_id)
        if not data:
            return None
        return StudentProfile(
            student_id=data["student_id"],
            account_id=data.get("account_id", ""),
            name=data.get("name", ""),
            parent_account_id=data.get("parent_account_id"),
            coach_id=data.get("coach_id"),
            level=data.get("level", "Beginner"),
            rating=data.get("rating", 1000),
            status=data.get("status", "active"),
        )

    async def get_coach_profile(self, coach_id: str) -> CoachProfile | None:
        await self._simulate_wait()
        # Find account with matching coach_id or account_id
        for acc in self._accounts.values():
            if acc.get("coach_id") == coach_id or acc.get("account_id") == coach_id:
                return CoachProfile(
                    coach_id=acc.get("coach_id", coach_id),
                    account_id=acc["account_id"],
                    name=acc.get("name", ""),
                    assigned_students=acc.get("assigned_students", []),
                    org_id=acc.get("org_id"),
                )
        return None

    async def get_children_for_parent(self, parent_id: str) -> list[StudentProfile]:
        await self._simulate_wait()
        parent_acc = self._accounts.get(parent_id)
        if not parent_acc:
            return []
        child_ids = parent_acc.get("children", [])
        res = []
        for cid in child_ids:
            stu = await self.get_student_profile(cid)
            if stu:
                res.append(stu)
        return res

    async def get_session_status(
        self, student_id: str, session_id: str | None = None
    ) -> SessionInfo | None:
        await self._simulate_wait()
        student_sessions = self._sessions.get(student_id, [])
        if not student_sessions:
            return None

        target = None
        if session_id:
            for s in student_sessions:
                if s["session_id"] == session_id:
                    target = s
                    break
        else:
            # Return latest / first upcoming session
            target = student_sessions[0]

        if not target:
            return None

        return SessionInfo(
            session_id=target["session_id"],
            student_id=target["student_id"],
            title=target.get("title", "Chess Session"),
            start_time=target.get("start_time", ""),
            status=target.get("status", "unknown"),
            reason_if_unavailable=target.get("reason_if_unavailable"),
            coach_id=target.get("coach_id"),
        )

    async def get_lesson_status(
        self, student_id: str, lesson_id: str | None = None
    ) -> SessionInfo | None:
        return await self.get_session_status(student_id, lesson_id)

    async def get_subscription_status(
        self, account_id: str
    ) -> SubscriptionInfo | None:
        await self._simulate_wait()
        data = self._subscriptions.get(account_id)
        if not data:
            return None
        return SubscriptionInfo(
            account_id=data["account_id"],
            plan_id=data.get("plan_id", ""),
            plan_name=data.get("plan_name", "Standard"),
            status=data.get("status", "active"),
            billing_cycle=data.get("billing_cycle", "monthly"),
            renewal_date=data.get("renewal_date", ""),
        )

    async def get_account_status(self, account_id: str) -> dict[str, Any] | None:
        await self._simulate_wait()
        data = self._accounts.get(account_id)
        if not data:
            return None
        return {
            "account_id": data["account_id"],
            "status": data.get("status", "active"),
            "role": data.get("role", "unknown"),
            "created_at": data.get("created_at", ""),
        }
