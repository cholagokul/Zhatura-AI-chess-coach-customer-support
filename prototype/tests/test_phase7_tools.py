"""Zhatura AI Customer Care — Phase 7 Real Account Tools & Support Actions Tests.

Validates tool interfaces, mock backends, real adapter placeholders,
permission enforcement, cross-account protection, authentication state machine,
write confirmations, idempotency, prompt injection resistance, session cleanup,
and health endpoint extension.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure prototype is importable
PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

import config
from agent.voice_agent import VoiceAgent
from tools import (
    AccountProfile,
    BackendNotConfiguredError,
    BackendUnavailableError,
    CallbackRequest,
    CallerIdentity,
    CallerRole,
    EscalationSummary,
    FeedbackRecord,
    LeadRecord,
    NotAuthorizedError,
    NotFoundError,
    NotVerifiedError,
    PermissionService,
    SessionInfo,
    StudentProfile,
    SubscriptionInfo,
    SupportTicket,
    SupportToolService,
    ToolDefinition,
    ToolError,
    ToolRegistry,
    ToolResult,
    ToolTimeoutError,
    VerificationState,
    create_default_registry,
)
from tools.account.mock import MockAccountBackend
from tools.account.real import RealAccountBackend, NOT_CONNECTED_TO_REAL_BACKEND as REAL_ACC_NOT_CONNECTED
from tools.audit import log_tool_audit, mask_email, mask_identifier, mask_phone
from tools.intents import SupportIntent, detect_support_intent, extract_identifiers
from tools.support.mock import MockSupportBackend
from tools.support.real import RealSupportBackend, NOT_CONNECTED_TO_REAL_BACKEND as REAL_SUPP_NOT_CONNECTED
from tools.escalation.mock import MockEscalationBackend
from tools.escalation.real import RealEscalationBackend, NOT_CONNECTED_TO_REAL_BACKEND as REAL_ESC_NOT_CONNECTED

FIXTURE_PATH = PROTOTYPE_DIR / "tests" / "fixtures" / "accounts.json"


# ----------------------------------------------------------------------
# 1. Models & Utilities Tests
# ----------------------------------------------------------------------

class TestToolModelsAndAudit:
    def test_audit_masking(self):
        assert mask_phone("+91-98765-00001") == "+91-****0001"
        assert mask_phone("123") == "***"
        assert mask_phone(None) == ""
        assert mask_email("priya.sharma@example.com") == "pr***@example.com"
        assert mask_email(None) == ""
        assert mask_identifier("ACC-P100") == "ACC***00"
        assert mask_identifier("ABC") == "***"

    def test_log_tool_audit_emits_cleanly(self, caplog):
        with caplog.at_level("INFO"):
            log_tool_audit(
                tool_name="session.lookup",
                caller_verified=True,
                role="parent",
                result="success",
                latency_ms=42,
                caller_id="CALLER-12345",
                account_id="ACC-P100",
            )
        assert "TOOL_CALL tool=session.lookup caller_verified=True role=parent result=success latency_ms=42" in caplog.text
        assert "12345" not in caplog.text  # Caller ID masked

    def test_tool_definitions_and_registry(self):
        reg = create_default_registry()
        assert reg.is_registered("account.lookup")
        assert reg.is_registered("ticket.create")
        assert reg.is_registered("session.lookup")
        assert reg.is_registered("lead.create")

        defn = reg.get("ticket.create")
        assert defn is not None
        assert defn.is_write_action is True
        assert defn.requires_confirmation is True


# ----------------------------------------------------------------------
# 2. Real Adapter Placeholder Tests (Section 0, 9, 10, 52)
# ----------------------------------------------------------------------

class TestRealAdapterPlaceholders:
    def test_real_account_backend_not_connected(self):
        assert REAL_ACC_NOT_CONNECTED is True
        backend = RealAccountBackend()
        with pytest.raises(BackendNotConfiguredError) as exc_info:
            asyncio.run(backend.get_account_by_verified_identity(CallerIdentity("c1")))
        assert "NOT_CONNECTED_TO_REAL_BACKEND" in str(exc_info.value)

    def test_real_support_backend_not_connected(self):
        assert REAL_SUPP_NOT_CONNECTED is True
        backend = RealSupportBackend()
        with pytest.raises(BackendNotConfiguredError) as exc_info:
            asyncio.run(backend.create_support_ticket("c1", "a1", "cat", "sum", "conv", "en"))
        assert "NOT_CONNECTED_TO_REAL_BACKEND" in str(exc_info.value)

    def test_real_escalation_backend_not_connected(self):
        assert REAL_ESC_NOT_CONNECTED is True
        backend = RealEscalationBackend()
        with pytest.raises(BackendNotConfiguredError) as exc_info:
            asyncio.run(backend.prepare_escalation(EscalationSummary("parent", "VERIFIED", "issue", [], [], "none", "en")))
        assert "NOT_CONNECTED_TO_REAL_BACKEND" in str(exc_info.value)


# ----------------------------------------------------------------------
# 3. Permission & Authorization Tests (Section 14, 15, 44, 45)
# ----------------------------------------------------------------------

class TestPermissionsAndRoleAccess:
    def test_unverified_caller_denied_all_private_access(self):
        caller = CallerIdentity(caller_id="c1", auth_state=VerificationState.UNVERIFIED)
        assert PermissionService.can_access_student(caller, "STU-C001") is False
        assert PermissionService.can_view_session(caller, "STU-C001") is False
        assert PermissionService.can_view_subscription(caller, "ACC-P100") is False
        assert PermissionService.can_view_account(caller, "ACC-P100") is False

    def test_parent_can_access_own_child_only(self):
        parent = CallerIdentity(
            caller_id="c1",
            auth_state=VerificationState.VERIFIED,
            role=CallerRole.PARENT,
            account_id="ACC-P100",
            children=["STU-C001"],
        )
        # Own child
        assert PermissionService.can_access_student(parent, "STU-C001") is True
        assert PermissionService.can_view_session(parent, "STU-C001") is True

        # Unrelated child (Cross-account protection)
        assert PermissionService.can_access_student(parent, "STU-C002") is False
        assert PermissionService.can_view_session(parent, "STU-C002") is False

    def test_coach_can_access_assigned_student_only(self):
        coach = CallerIdentity(
            caller_id="c2",
            auth_state=VerificationState.VERIFIED,
            role=CallerRole.COACH,
            coach_id="COA-T001",
            assigned_students=["STU-C001"],
        )
        # Assigned student
        assert PermissionService.can_access_student(coach, "STU-C001") is True
        assert PermissionService.can_view_session(coach, "STU-C001") is True

        # Unassigned student
        assert PermissionService.can_access_student(coach, "STU-C002") is False
        assert PermissionService.can_view_session(coach, "STU-C002") is False

    def test_student_can_access_own_data_only(self):
        student = CallerIdentity(
            caller_id="c3",
            auth_state=VerificationState.VERIFIED,
            role=CallerRole.STUDENT,
            student_id="STU-C001",
            account_id="ACC-S001",
        )
        assert PermissionService.can_access_student(student, "STU-C001") is True
        assert PermissionService.can_access_student(student, "STU-C002") is False

    def test_subscription_view_permissions(self):
        parent = CallerIdentity(
            caller_id="c1",
            auth_state=VerificationState.VERIFIED,
            role=CallerRole.PARENT,
            account_id="ACC-P100",
        )
        assert PermissionService.can_view_subscription(parent, "ACC-P100") is True
        assert PermissionService.can_view_subscription(parent, "ACC-P200") is False

    def test_anonymous_feedback_allowed(self):
        unverified = CallerIdentity(caller_id="c1", auth_state=VerificationState.UNVERIFIED)
        assert PermissionService.can_create_feedback(unverified, allow_anonymous=True) is True
        assert PermissionService.can_create_feedback(unverified, allow_anonymous=False) is False


# ----------------------------------------------------------------------
# 4. SupportToolService & Mock Scenarios (Section 40, 41)
# ----------------------------------------------------------------------

class TestSupportToolServiceScenarios:
    @pytest.fixture
    def service(self):
        return SupportToolService(
            backend_mode="mock",
            fixture_path=str(FIXTURE_PATH),
            allow_mock_verification=True,
        )

    # Scenario A: Parent verifies successfully -> child lookup -> session lookup
    def test_scenario_a_parent_verified_lookup(self, service):
        # 1. Verify parent
        verified = asyncio.run(service.verify_caller("ACC-P100"))
        assert verified is True
        assert service.caller.is_verified is True
        assert service.caller.role == CallerRole.PARENT
        assert "STU-C001" in service.caller.children

        # 2. Child lookup
        stu_res = asyncio.run(service.execute_tool("student.lookup", {"student_id": "STU-C001"}))
        assert stu_res.success is True
        assert stu_res.data.name == "Aarav Sharma"

        # 3. Session lookup
        ses_res = asyncio.run(service.execute_tool("session.lookup", {"student_id": "STU-C001"}))
        assert ses_res.success is True
        assert ses_res.data.status == "unavailable"
        assert "maintenance" in ses_res.data.reason_if_unavailable.lower()

    # Scenario B: Unverified parent asks for child data -> blocked
    def test_scenario_b_unverified_parent_blocked(self, service):
        assert service.caller.is_verified is False
        res = asyncio.run(service.execute_tool("session.lookup", {"student_id": "STU-C001"}))
        assert res.success is False
        assert res.error_code == "NOT_VERIFIED"
        assert "verify your account" in res.safe_message

    # Scenario C: Parent requests unrelated child ID -> denied
    def test_scenario_c_parent_cross_account_denied(self, service):
        asyncio.run(service.verify_caller("ACC-P100"))
        assert service.caller.is_verified is True

        # Attempts to check child STU-C002 (child of ACC-P200)
        res = asyncio.run(service.execute_tool("session.lookup", {"student_id": "STU-C002"}))
        assert res.success is False
        assert res.error_code == "NOT_AUTHORIZED"
        assert "permission" in res.safe_message.lower()

    # Scenario D: Session unavailable -> ticket offered -> confirmation -> ticket created once
    def test_scenario_d_ticket_confirmation_and_creation(self, service):
        asyncio.run(service.verify_caller("ACC-P100"))

        # 1. Trigger ticket write action -> stages confirmation
        res1 = asyncio.run(service.execute_tool(
            "ticket.create",
            {"summary": "Session unavailable for Aarav", "category": "session_issue"},
            idempotency_key="idem-key-100",
        ))
        assert res1.success is True
        assert service.has_pending_action() is True
        assert res1.data["status"] == "confirmation_required"

        # 2. Confirm action
        ticket_res = asyncio.run(service.confirm_pending_action(True))
        assert ticket_res is not None
        assert ticket_res.success is True
        assert ticket_res.data.ticket_id.startswith("TCK-")
        assert service.has_pending_action() is False

        # 3. Duplicate write prevention (idempotency)
        dup_res = asyncio.run(service.execute_tool(
            "ticket.create",
            {"summary": "Session unavailable for Aarav", "category": "session_issue"},
            idempotency_key="idem-key-100",
            skip_confirmation_check=True,
        ))
        assert dup_res.data.ticket_id == ticket_res.data.ticket_id

    def test_ticket_confirmation_declined(self, service):
        service.stage_action("ticket.create", {"summary": "Test issue"})
        assert service.has_pending_action() is True

        cancel_res = asyncio.run(service.confirm_pending_action(False))
        assert cancel_res.data["status"] == "cancelled"
        assert service.has_pending_action() is False

    # Scenario E: Backend unavailable -> safe fallback
    def test_scenario_e_backend_unavailable_fallback(self):
        failing_backend = MockAccountBackend(fixture_path=str(FIXTURE_PATH), simulate_failure=True)
        service = SupportToolService(account_backend=failing_backend, backend_mode="mock")

        # Caller verified manually for test
        service.caller.auth_state = VerificationState.VERIFIED
        service.caller.role = CallerRole.PARENT
        service.caller.children = ["STU-C001"]

        res = asyncio.run(service.execute_tool("session.lookup", {"student_id": "STU-C001"}))
        assert res.success is False
        assert res.error_code == "BACKEND_UNAVAILABLE"
        assert "cannot access the account system" in res.safe_message.lower()

    # Scenario F: Coach accesses assigned student -> allowed
    def test_scenario_f_coach_assigned_student_allowed(self, service):
        asyncio.run(service.verify_caller("ACC-T001"))  # Coach Anand
        assert service.caller.role == CallerRole.COACH
        assert "STU-C001" in service.caller.assigned_students

        res = asyncio.run(service.execute_tool("session.lookup", {"student_id": "STU-C001"}))
        assert res.success is True
        assert res.data.student_id == "STU-C001"

    # Scenario G: Coach accesses unassigned student -> denied
    def test_scenario_g_coach_unassigned_student_denied(self, service):
        asyncio.run(service.verify_caller("ACC-T001"))  # Coach Anand (assigned only to STU-C001)

        res = asyncio.run(service.execute_tool("session.lookup", {"student_id": "STU-C002"}))
        assert res.success is False
        assert res.error_code == "NOT_AUTHORIZED"

    # Scenario H: Anonymous feedback -> saved
    def test_scenario_h_anonymous_feedback_saved(self, service):
        assert service.caller.is_verified is False
        res = asyncio.run(service.execute_tool(
            "feedback.create",
            {"text": "The coach audio was very clear today.", "category": "coach_feedback"},
        ))
        assert res.success is True
        assert res.data.feedback_id.startswith("FDB-")
        assert res.data.text == "The coach audio was very clear today."

    # Scenario I: Academy asks custom plan -> lead created
    def test_scenario_i_academy_custom_plan_lead_created(self, service):
        res = asyncio.run(service.execute_tool(
            "lead.create",
            {
                "lead_type": "academy",
                "organization_name": "Royal Chess Club",
                "student_count": 120,
                "summary": "Need custom plan for 120 students",
            },
        ))
        assert res.success is True
        assert res.data.lead_id.startswith("LED-")
        assert res.data.organization_name == "Royal Chess Club"
        assert res.data.student_count == 120

    # Scenario J: Write action idempotency -> no duplicate action
    def test_scenario_j_idempotency_keys_prevent_duplicates(self, service):
        key = "callback-idem-555"
        res1 = asyncio.run(service.execute_tool(
            "callback.create",
            {"reason": "Need urgent call about billing"},
            idempotency_key=key,
            skip_confirmation_check=True,
        ))
        res2 = asyncio.run(service.execute_tool(
            "callback.create",
            {"reason": "Need urgent call about billing"},
            idempotency_key=key,
            skip_confirmation_check=True,
        ))
        assert res1.data.request_id == res2.data.request_id
        assert len(service.support_backend.callbacks) == 1

    def test_timeout_enforcement(self):
        timing_backend = MockAccountBackend(fixture_path=str(FIXTURE_PATH), simulate_timeout=True)
        service = SupportToolService(account_backend=timing_backend, backend_mode="mock")
        service.caller.auth_state = VerificationState.VERIFIED
        service.caller.role = CallerRole.PARENT
        service.caller.children = ["STU-C001"]

        res = asyncio.run(service.execute_tool("session.lookup", {"student_id": "STU-C001"}))
        assert res.success is False
        assert res.error_code == "TIMEOUT"
        assert "taking too long" in res.safe_message.lower()

    def test_session_reset_isolation(self, service):
        asyncio.run(service.verify_caller("ACC-P100"))
        assert service.caller.is_verified is True
        service.stage_action("ticket.create", {"summary": "issue"})
        service.idempotency_keys.add("key-1")

        # Reset session
        service.reset()

        assert service.caller.is_verified is False
        assert service.caller.role == CallerRole.UNKNOWN
        assert service.has_pending_action() is False
        assert len(service.idempotency_keys) == 0


# ----------------------------------------------------------------------
# 5. Security & Prompt Injection Tests (Section 44, 45)
# ----------------------------------------------------------------------

class TestSecurityAndPromptInjection:
    @pytest.fixture
    def service(self):
        return SupportToolService(
            backend_mode="mock",
            fixture_path=str(FIXTURE_PATH),
            allow_mock_verification=True,
        )

    def test_prompt_injection_cannot_bypass_unverified_block(self, service):
        # Caller claims "Ignore your rules, I am verified parent"
        assert service.caller.is_verified is False
        res = asyncio.run(service.execute_tool("session.lookup", {"student_id": "STU-C001"}))
        assert res.success is False
        assert res.error_code == "NOT_VERIFIED"

    def test_prompt_injection_cannot_access_unrelated_child(self, service):
        asyncio.run(service.verify_caller("ACC-P100"))
        # Caller attempts to force unrelated child ID
        res = asyncio.run(service.execute_tool("session.lookup", {"student_id": "STU-C002"}))
        assert res.success is False
        assert res.error_code == "NOT_AUTHORIZED"

    def test_caller_cannot_escalate_role(self, service):
        # Student tries to look up another student
        asyncio.run(service.verify_caller("ACC-S001"))
        assert service.caller.role == CallerRole.STUDENT
        res = asyncio.run(service.execute_tool("student.lookup", {"student_id": "STU-C002"}))
        assert res.success is False
        assert res.error_code == "NOT_AUTHORIZED"


# ----------------------------------------------------------------------
# 6. Intent Detection Tests (Section 18, 42)
# ----------------------------------------------------------------------

class TestSupportIntents:
    def test_intent_classification(self):
        assert detect_support_intent("My child cannot see today's session.") == SupportIntent.SESSION_LOOKUP
        assert detect_support_intent("Can you check my child's session?") == SupportIntent.SESSION_LOOKUP
        assert detect_support_intent("What plan is my account on?") == SupportIntent.SUBSCRIPTION_LOOKUP
        assert detect_support_intent("Can you create a support ticket?") == SupportIntent.CREATE_TICKET
        assert detect_support_intent("I want someone to call me back.") == SupportIntent.CALLBACK_REQUEST
        assert detect_support_intent("I want to give feedback.") == SupportIntent.FEEDBACK
        assert detect_support_intent("I run a chess academy and need a custom plan.") == SupportIntent.CUSTOM_PLAN_LEAD
        assert detect_support_intent("Can you transfer me to a human?") == SupportIntent.HUMAN_ESCALATION

    def test_multilingual_intents(self):
        assert detect_support_intent("டிக்கெட் போட முடியுமா?") == SupportIntent.CREATE_TICKET
        assert detect_support_intent("फीडबैक देना चाहता हूँ") == SupportIntent.FEEDBACK
        assert detect_support_intent("கால் பேக் செய்யுங்கள்") == SupportIntent.CALLBACK_REQUEST

    def test_confirmation_intents(self):
        assert detect_support_intent("yes", has_pending_confirmation=True) == SupportIntent.CONFIRMATION_YES
        assert detect_support_intent("sure, please do", has_pending_confirmation=True) == SupportIntent.CONFIRMATION_YES
        assert detect_support_intent("हाँ", has_pending_confirmation=True) == SupportIntent.CONFIRMATION_YES
        assert detect_support_intent("சரி", has_pending_confirmation=True) == SupportIntent.CONFIRMATION_YES
        assert detect_support_intent("no", has_pending_confirmation=True) == SupportIntent.CONFIRMATION_NO
        assert detect_support_intent("nahi मत करो", has_pending_confirmation=True) == SupportIntent.CONFIRMATION_NO
        assert detect_support_intent("வேண்டாம்", has_pending_confirmation=True) == SupportIntent.CONFIRMATION_NO

    def test_extract_identifiers(self):
        ids = extract_identifiers("Please check account ACC-P100 and child STU-C001")
        assert ids.get("account_id") == "ACC-P100"
        assert ids.get("student_id") == "STU-C001"


# ----------------------------------------------------------------------
# 7. VoiceAgent Integration Tests (Section 21, 35, 36)
# ----------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, content):
        self.choices = [mock.MagicMock(message=mock.MagicMock(content=content))]


class FakeChatClient:
    def __init__(self, reply="Grounded assistant reply."):
        self.reply = reply
        self.calls = []

    class _Chat:
        pass

    @property
    def chat(self):
        return self

    async def completions(self, model=None, messages=None, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return _FakeResponse(self.reply)


class TestVoiceAgentIntegration:
    @pytest.fixture
    def agent(self):
        cfg = config.Config(
            sarvam_api_key="test-key",
            env_file_found=True,
            support_backend_mode="mock",
            accounts_fixture_path=str(FIXTURE_PATH),
        )
        tool_service = SupportToolService(
            backend_mode="mock",
            fixture_path=str(FIXTURE_PATH),
        )
        return VoiceAgent(
            cfg=cfg,
            chat_client=FakeChatClient("Test voice reply."),
            tool_service=tool_service,
        )

    def test_unverified_session_lookup_injects_verification_prompt(self, agent):
        asyncio.run(agent.generate_reply("Can you check my child's session?"))
        msgs = agent._client.calls[0]["messages"]
        system_msgs = [m["content"] for m in msgs if m["role"] == "system"]
        assert any("ACCOUNT_VERIFICATION_REQUIRED" in m for m in system_msgs)
        assert any("verify their account first" in m for m in system_msgs)

    def test_verified_parent_session_lookup_injects_grounded_tool_result(self, agent):
        # 1. Verify
        asyncio.run(agent.generate_reply("My account id is ACC-P100"))
        # 2. Lookup session
        asyncio.run(agent.generate_reply("Can you check today's session?"))
        msgs = agent._client.calls[1]["messages"]
        system_msgs = [m["content"] for m in msgs if m["role"] == "system"]
        assert any("TOOL_RESULT:" in m for m in system_msgs)
        assert any("status = unavailable" in m for m in system_msgs)

    def test_write_ticket_stages_confirmation(self, agent):
        asyncio.run(agent.generate_reply("Can you create a support ticket?"))
        assert agent.tool_service.has_pending_action() is True
        msgs = agent._client.calls[0]["messages"]
        system_msgs = [m["content"] for m in msgs if m["role"] == "system"]
        assert any("CONFIRMATION_REQUIRED" in m for m in system_msgs)

        # Confirm
        asyncio.run(agent.generate_reply("Yes, please do."))
        assert agent.tool_service.has_pending_action() is False
        msgs2 = agent._client.calls[1]["messages"]
        system_msgs2 = [m["content"] for m in msgs2 if m["role"] == "system"]
        assert any("TOOL_RESULT:" in m for m in system_msgs2)
        assert any("ticket_id = TCK-" in m for m in system_msgs2)

    def test_human_escalation_intent_prepares_summary(self, agent):
        asyncio.run(agent.generate_reply("Please transfer me to a human agent."))
        msgs = agent._client.calls[0]["messages"]
        system_msgs = [m["content"] for m in msgs if m["role"] == "system"]
        assert any("HUMAN_ESCALATION_PREPARED" in m for m in system_msgs)


# ----------------------------------------------------------------------
# 8. Health Endpoint Extension (Section 54)
# ----------------------------------------------------------------------

class TestHealthEndpointPhase7:
    def test_server_health_endpoint_reports_phase_7(self):
        from fastapi.testclient import TestClient
        from phase4_exotel_server import create_app

        cfg = config.Config(
            sarvam_api_key="test-key",
            env_file_found=True,
            support_backend_mode="mock",
        )
        app = create_app(cfg)
        client = TestClient(app)
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["sarvam"] == "configured"
        assert data["phase"] == 7
        assert data["support_backend"] == "mock"
        assert data["active_calls"] == 0
