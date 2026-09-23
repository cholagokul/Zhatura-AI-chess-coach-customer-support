"""Zhatura AI Customer Care — Support Tool Service (Phase 7).

Central orchestrator for caller verification, role-based authorization,
tool execution, write confirmations, idempotency, and audit logging.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from .account.interface import AccountBackendInterface
from .account.mock import MockAccountBackend
from .account.real import RealAccountBackend
from .audit import log_tool_audit, mask_identifier
from .errors import (
    BackendNotConfiguredError,
    BackendUnavailableError,
    NotAuthorizedError,
    NotFoundError,
    NotVerifiedError,
    ToolError,
    ToolTimeoutError,
)
from .escalation.interface import EscalationBackendInterface
from .escalation.mock import MockEscalationBackend
from .escalation.real import RealEscalationBackend
from .models import (
    CallerIdentity,
    CallerRole,
    EscalationSummary,
    ToolResult,
    VerificationState,
)
from .permissions import PermissionService
from .registry import ToolDefinition, ToolRegistry, create_default_registry
from .support.interface import SupportBackendInterface
from .support.mock import MockSupportBackend
from .support.real import RealSupportBackend

logger = logging.getLogger("tools.service")


class SupportToolService:
    """Session-scoped facade for customer account and support actions."""

    def __init__(
        self,
        session_id: str | None = None,
        account_backend: AccountBackendInterface | None = None,
        support_backend: SupportBackendInterface | None = None,
        escalation_backend: EscalationBackendInterface | None = None,
        backend_mode: str = "mock",
        fixture_path: str | None = None,
        registry: ToolRegistry | None = None,
        allow_mock_verification: bool = True,
    ):
        self.session_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"
        self.backend_mode = backend_mode
        self.allow_mock_verification = allow_mock_verification
        self.registry = registry or create_default_registry()

        # Initialize backends based on mode
        if account_backend is not None:
            self.account_backend = account_backend
        elif backend_mode == "mock":
            self.account_backend = MockAccountBackend(fixture_path=fixture_path)
        elif backend_mode == "real":
            self.account_backend = RealAccountBackend()
        else:
            self.account_backend = None

        if support_backend is not None:
            self.support_backend = support_backend
        elif backend_mode == "mock":
            self.support_backend = MockSupportBackend()
        elif backend_mode == "real":
            self.support_backend = RealSupportBackend()
        else:
            self.support_backend = None

        if escalation_backend is not None:
            self.escalation_backend = escalation_backend
        elif backend_mode == "mock":
            self.escalation_backend = MockEscalationBackend()
        elif backend_mode == "real":
            self.escalation_backend = RealEscalationBackend()
        else:
            self.escalation_backend = None

        # Per-session authentication and workflow state
        self.caller: CallerIdentity = CallerIdentity(caller_id=f"caller-{self.session_id}")
        self.pending_action: dict[str, Any] | None = None
        self.idempotency_keys: set[str] = set()
        self.last_tool_result: ToolResult | None = None
        self.last_error: str | None = None

    # ------------------------------------------------------------------
    # Authentication & Verification
    # ------------------------------------------------------------------

    async def verify_caller(
        self,
        identifier: str,
        role_hint: CallerRole | None = None,
        token: str | None = None,
    ) -> bool:
        """Attempt to verify the caller's identity.

        In mock mode (dev/testing), matches synthetic accounts by ID or phone.
        Never fakes verification if backend is unavailable.
        """
        clean_id = identifier.strip().upper()
        logger.info(
            "[%s] Caller verification attempt for identifier: %s",
            self.session_id,
            mask_identifier(clean_id),
        )
        self.caller.auth_state = VerificationState.VERIFICATION_PENDING

        if self.backend_mode != "mock" and not self.allow_mock_verification:
            # Production without real OTP is not configured
            self.caller.auth_state = VerificationState.VERIFICATION_FAILED
            return False

        if not self.account_backend:
            self.caller.auth_state = VerificationState.VERIFICATION_FAILED
            return False

        try:
            # Try lookup as account_id
            temp_identity = CallerIdentity(
                caller_id=self.caller.caller_id,
                account_id=clean_id,
                phone=identifier.strip(),
            )
            account = await self.account_backend.get_account_by_verified_identity(temp_identity)

            if not account and clean_id.startswith("STU-"):
                # Caller gave student ID
                stu = await self.account_backend.get_student_profile(clean_id)
                if stu:
                    account = await self.account_backend.get_account_by_verified_identity(
                        CallerIdentity(caller_id=self.caller.caller_id, account_id=stu.account_id)
                    )

            if not account and clean_id.startswith("COA-"):
                # Caller gave coach ID
                coach = await self.account_backend.get_coach_profile(clean_id)
                if coach:
                    account = await self.account_backend.get_account_by_verified_identity(
                        CallerIdentity(caller_id=self.caller.caller_id, account_id=coach.account_id)
                    )

            if account:
                self.caller.auth_state = VerificationState.VERIFIED
                self.caller.role = account.role
                self.caller.account_id = account.account_id
                self.caller.name = account.name
                self.caller.phone = account.phone
                self.caller.children = list(account.children)
                self.caller.assigned_students = list(account.assigned_students)
                self.caller.org_id = account.org_id
                logger.info(
                    "[%s] Caller VERIFIED as role=%s (account=%s).",
                    self.session_id,
                    account.role.value,
                    account.account_id,
                )
                return True

            self.caller.auth_state = VerificationState.VERIFICATION_FAILED
            logger.info("[%s] Verification failed: account not found.", self.session_id)
            return False

        except Exception as exc:
            logger.error("[%s] Verification exception: %s", self.session_id, type(exc).__name__)
            self.caller.auth_state = VerificationState.VERIFICATION_FAILED
            return False

    # ------------------------------------------------------------------
    # Confirmation Management (Write Actions)
    # ------------------------------------------------------------------

    def stage_action(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> None:
        """Stage a write action awaiting caller confirmation."""
        self.pending_action = {
            "tool_name": tool_name,
            "arguments": arguments,
            "idempotency_key": idempotency_key or f"idem-{uuid.uuid4().hex[:8]}",
            "staged_at": time.time(),
        }
        logger.info(
            "[%s] STAGED action %s (key=%s).",
            self.session_id,
            tool_name,
            self.pending_action["idempotency_key"],
        )

    def has_pending_action(self) -> bool:
        return self.pending_action is not None

    def cancel_pending_action(self) -> None:
        if self.pending_action:
            logger.info(
                "[%s] CANCELLED staged action %s.",
                self.session_id,
                self.pending_action["tool_name"],
            )
            self.pending_action = None

    async def confirm_pending_action(self, confirmed: bool) -> ToolResult | None:
        """Execute or discard the currently staged write action."""
        if not self.pending_action:
            return None

        staged = self.pending_action
        self.pending_action = None

        if not confirmed:
            logger.info("[%s] Action declined by caller: %s", self.session_id, staged["tool_name"])
            return ToolResult(
                success=True,
                verified=self.caller.is_verified,
                source="tool_service",
                safe_message="Action was cancelled per your request.",
                data={"status": "cancelled"},
            )

        logger.info("[%s] Action confirmed by caller. Executing %s...", self.session_id, staged["tool_name"])
        return await self.execute_tool(
            tool_name=staged["tool_name"],
            arguments=staged["arguments"],
            idempotency_key=staged["idempotency_key"],
            skip_confirmation_check=True,
        )

    # ------------------------------------------------------------------
    # Tool Execution
    # ------------------------------------------------------------------

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        skip_confirmation_check: bool = False,
    ) -> ToolResult:
        """Execute a tool with permissions, timeouts, and audit logging."""
        arguments = arguments or {}
        t0 = time.monotonic()
        defn = self.registry.get(tool_name)

        if not defn:
            latency_ms = round((time.monotonic() - t0) * 1000)
            log_tool_audit(tool_name, self.caller.is_verified, self.caller.role.value, "error", latency_ms, error_code="INVALID_REQUEST")
            return ToolResult(
                success=False,
                verified=self.caller.is_verified,
                source="tool_service",
                error_code="INVALID_REQUEST",
                safe_message=f"Tool {tool_name} is not recognized.",
            )

        # Verification check
        if defn.requires_verification and not self.caller.is_verified:
            latency_ms = round((time.monotonic() - t0) * 1000)
            log_tool_audit(tool_name, False, self.caller.role.value, "denied", latency_ms, error_code="NOT_VERIFIED")
            return ToolResult(
                success=False,
                verified=False,
                source="tool_service",
                error_code="NOT_VERIFIED",
                safe_message="I need to verify your account before accessing those details.",
            )

        # Confirmation gate for write actions
        if defn.requires_confirmation and not skip_confirmation_check:
            self.stage_action(tool_name, arguments, idempotency_key)
            latency_ms = round((time.monotonic() - t0) * 1000)
            log_tool_audit(tool_name, self.caller.is_verified, self.caller.role.value, "staged", latency_ms)
            return ToolResult(
                success=True,
                verified=self.caller.is_verified,
                source="tool_service",
                data={"status": "confirmation_required", "tool": tool_name},
                safe_message=f"Confirmation required before executing {tool_name}.",
            )

        # Idempotency check for committed write actions
        if defn.is_write_action and idempotency_key:
            if idempotency_key in self.idempotency_keys:
                logger.info("[%s] Duplicate write action prevented by idempotency key: %s", self.session_id, idempotency_key)
            self.idempotency_keys.add(idempotency_key)

        # Execute with timeout
        timeout = defn.timeout_seconds
        try:
            res = await asyncio.wait_for(
                self._dispatch(defn, arguments, idempotency_key),
                timeout=timeout,
            )
            latency_ms = round((time.monotonic() - t0) * 1000)
            log_tool_audit(
                tool_name,
                self.caller.is_verified,
                self.caller.role.value,
                "success" if res.success else "denied" if res.error_code == "NOT_AUTHORIZED" else "error",
                latency_ms,
                caller_id=self.caller.caller_id,
                account_id=self.caller.account_id,
                error_code=res.error_code,
            )
            self.last_tool_result = res
            return res

        except asyncio.TimeoutError:
            latency_ms = round((time.monotonic() - t0) * 1000)
            log_tool_audit(tool_name, self.caller.is_verified, self.caller.role.value, "timeout", latency_ms, error_code="TIMEOUT")
            return ToolResult(
                success=False,
                verified=self.caller.is_verified,
                source=f"{self.backend_mode}_backend",
                error_code="TIMEOUT",
                safe_message="The support system is temporarily taking too long. Please try again in a moment.",
            )

        except ToolError as te:
            latency_ms = round((time.monotonic() - t0) * 1000)
            log_tool_audit(tool_name, self.caller.is_verified, self.caller.role.value, "error", latency_ms, error_code=te.code)
            return ToolResult(
                success=False,
                verified=self.caller.is_verified,
                source=f"{self.backend_mode}_backend",
                error_code=te.code,
                safe_message=te.safe_message,
            )

        except Exception as exc:
            latency_ms = round((time.monotonic() - t0) * 1000)
            logger.exception("[%s] Unexpected error in tool %s", self.session_id, tool_name)
            log_tool_audit(tool_name, self.caller.is_verified, self.caller.role.value, "error", latency_ms, error_code="INTERNAL_ERROR")
            return ToolResult(
                success=False,
                verified=self.caller.is_verified,
                source=f"{self.backend_mode}_backend",
                error_code="INTERNAL_ERROR",
                safe_message="I cannot access the account system right now.",
            )

    async def _dispatch(
        self,
        defn: ToolDefinition,
        args: dict[str, Any],
        idempotency_key: str | None,
    ) -> ToolResult:
        """Internal router to the appropriate backend method."""
        tool_name = defn.name

        # --- ACCOUNT LOOKUPS ---
        if tool_name == "account.lookup":
            target_acc = args.get("account_id") or self.caller.account_id
            if not PermissionService.can_view_account(self.caller, target_acc):
                return ToolResult(
                    success=False,
                    verified=self.caller.is_verified,
                    source=f"{self.backend_mode}_backend",
                    error_code="NOT_AUTHORIZED",
                    safe_message="You do not have permission to access this account.",
                )
            acc = await self.account_backend.get_account_by_verified_identity(
                CallerIdentity(caller_id=self.caller.caller_id, account_id=target_acc)
            )
            if not acc:
                return ToolResult(
                    success=False,
                    verified=self.caller.is_verified,
                    source=f"{self.backend_mode}_backend",
                    error_code="NOT_FOUND",
                    safe_message="Account not found.",
                )
            return ToolResult(
                success=True,
                verified=True,
                source=f"{self.backend_mode}_backend",
                data=acc,
                safe_message="Account details retrieved.",
            )

        if tool_name == "student.lookup":
            student_id = args.get("student_id")
            if not student_id and self.caller.children:
                student_id = self.caller.children[0]
            if not student_id:
                return ToolResult(
                    success=False,
                    verified=self.caller.is_verified,
                    source=f"{self.backend_mode}_backend",
                    error_code="INVALID_REQUEST",
                    safe_message="No student identifier provided.",
                )
            stu = await self.account_backend.get_student_profile(student_id)
            if not stu:
                return ToolResult(
                    success=False,
                    verified=self.caller.is_verified,
                    source=f"{self.backend_mode}_backend",
                    error_code="NOT_FOUND",
                    safe_message="Student profile not found.",
                )
            if not PermissionService.can_access_student(self.caller, student_id, stu):
                return ToolResult(
                    success=False,
                    verified=self.caller.is_verified,
                    source=f"{self.backend_mode}_backend",
                    error_code="NOT_AUTHORIZED",
                    safe_message="You do not have permission to access this student profile.",
                )
            return ToolResult(
                success=True,
                verified=True,
                source=f"{self.backend_mode}_backend",
                data=stu,
                safe_message="Student profile retrieved.",
            )

        if tool_name == "session.lookup":
            student_id = args.get("student_id")
            if not student_id and self.caller.children:
                student_id = self.caller.children[0]
            elif not student_id and self.caller.student_id:
                student_id = self.caller.student_id

            if not student_id:
                return ToolResult(
                    success=False,
                    verified=self.caller.is_verified,
                    source=f"{self.backend_mode}_backend",
                    error_code="INVALID_REQUEST",
                    safe_message="Please specify which student's session to check.",
                )

            # Permission check
            stu = await self.account_backend.get_student_profile(student_id)
            if not PermissionService.can_view_session(self.caller, student_id, stu):
                return ToolResult(
                    success=False,
                    verified=self.caller.is_verified,
                    source=f"{self.backend_mode}_backend",
                    error_code="NOT_AUTHORIZED",
                    safe_message="You do not have permission to view session details for this student.",
                )

            session = await self.account_backend.get_session_status(
                student_id=student_id, session_id=args.get("session_id")
            )
            if not session:
                return ToolResult(
                    success=False,
                    verified=self.caller.is_verified,
                    source=f"{self.backend_mode}_backend",
                    error_code="NOT_FOUND",
                    safe_message="No session records found for this student.",
                )
            return ToolResult(
                success=True,
                verified=True,
                source=f"{self.backend_mode}_backend",
                data=session,
                safe_message=f"Session status is {session.status}.",
            )

        if tool_name == "subscription.lookup":
            account_id = args.get("account_id") or self.caller.account_id
            if not PermissionService.can_view_subscription(self.caller, account_id):
                return ToolResult(
                    success=False,
                    verified=self.caller.is_verified,
                    source=f"{self.backend_mode}_backend",
                    error_code="NOT_AUTHORIZED",
                    safe_message="You do not have permission to view this subscription.",
                )
            sub = await self.account_backend.get_subscription_status(account_id)
            if not sub:
                return ToolResult(
                    success=False,
                    verified=self.caller.is_verified,
                    source=f"{self.backend_mode}_backend",
                    error_code="NOT_FOUND",
                    safe_message="Subscription details not found.",
                )
            return ToolResult(
                success=True,
                verified=True,
                source=f"{self.backend_mode}_backend",
                data=sub,
                safe_message=f"Subscription is currently {sub.status}.",
            )

        # --- SUPPORT ACTIONS ---
        if tool_name == "ticket.create":
            ticket = await self.support_backend.create_support_ticket(
                caller_id=self.caller.caller_id,
                account_id=self.caller.account_id,
                issue_category=args.get("category", "general_support"),
                summary=args.get("summary", "Customer request via voice AI"),
                conversation_summary=args.get("conversation_summary", ""),
                language=args.get("language", "en-IN"),
                priority=args.get("priority", "normal"),
                idempotency_key=idempotency_key,
            )
            return ToolResult(
                success=True,
                verified=self.caller.is_verified,
                source=f"{self.backend_mode}_backend",
                data=ticket,
                safe_message=f"Support ticket {ticket.ticket_id} has been created.",
            )

        if tool_name == "callback.create":
            cb = await self.support_backend.create_callback_request(
                caller_id=self.caller.caller_id,
                account_id=self.caller.account_id,
                reason=args.get("reason", "Customer requested phone callback"),
                preferred_language=args.get("language", "en-IN"),
                preferred_window=args.get("window", "earliest_available"),
                idempotency_key=idempotency_key,
            )
            return ToolResult(
                success=True,
                verified=self.caller.is_verified,
                source=f"{self.backend_mode}_backend",
                data=cb,
                safe_message=f"Callback request {cb.request_id} has been registered.",
            )

        if tool_name == "feedback.create":
            fb = await self.support_backend.save_feedback(
                caller_id=self.caller.caller_id,
                account_id=self.caller.account_id,
                text=args.get("text", ""),
                category=args.get("category", "general"),
                language=args.get("language", "en-IN"),
                idempotency_key=idempotency_key,
            )
            return ToolResult(
                success=True,
                verified=self.caller.is_verified,
                source=f"{self.backend_mode}_backend",
                data=fb,
                safe_message="Thank you for your feedback, it has been saved.",
            )

        if tool_name == "lead.create":
            lead_type = args.get("lead_type", "academy")
            if lead_type == "custom_plan":
                lead = await self.support_backend.create_custom_plan_lead(
                    organization_name=args.get("organization_name", "Prospective Organization"),
                    contact_info=args.get("contact_info", self.caller.phone or "voice_call"),
                    student_count=args.get("student_count"),
                    summary=args.get("summary", "Custom plan inquiry"),
                    preferred_language=args.get("language", "en-IN"),
                    idempotency_key=idempotency_key,
                )
            else:
                lead = await self.support_backend.create_academy_lead(
                    organization_name=args.get("organization_name", "Chess Academy"),
                    contact_info=args.get("contact_info", self.caller.phone or "voice_call"),
                    student_count=args.get("student_count"),
                    summary=args.get("summary", "Academy inquiry"),
                    preferred_language=args.get("language", "en-IN"),
                    idempotency_key=idempotency_key,
                )
            return ToolResult(
                success=True,
                verified=self.caller.is_verified,
                source=f"{self.backend_mode}_backend",
                data=lead,
                safe_message=f"Lead {lead.lead_id} recorded for our team.",
            )

        if tool_name == "escalation.prepare":
            summary = EscalationSummary(
                caller_role=self.caller.role.value,
                verification_status=self.caller.auth_state.value,
                issue=args.get("issue", "Unresolved caller request"),
                attempted_steps=args.get("attempted_steps", []),
                relevant_tool_results=args.get("relevant_tool_results", []),
                unresolved_reason=args.get("unresolved_reason", "Customer requested human representative"),
                language=args.get("language", "en-IN"),
                urgency=args.get("urgency", "medium"),
                ticket_id=args.get("ticket_id"),
            )
            if self.escalation_backend:
                await self.escalation_backend.prepare_escalation(summary)
            return ToolResult(
                success=True,
                verified=self.caller.is_verified,
                source=f"{self.backend_mode}_backend",
                data=summary,
                safe_message="Escalation summary has been prepared.",
            )

        raise ToolError(f"Unhandled tool: {tool_name}")

    # ------------------------------------------------------------------
    # Session Reset (Clean Cleanup on Hangup)
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Completely flush all session context, verification, and caches."""
        logger.info("[%s] Resetting SupportToolService session state.", self.session_id)
        self.caller = CallerIdentity(caller_id=f"caller-{self.session_id}")
        self.pending_action = None
        self.idempotency_keys.clear()
        self.last_tool_result = None
        self.last_error = None
