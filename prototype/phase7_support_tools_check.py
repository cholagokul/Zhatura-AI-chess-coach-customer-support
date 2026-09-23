"""Zhatura AI Customer Care — Phase 7 Support Tools Check (Section 50).

Validates:
- Scenario A: Parent verifies successfully -> child lookup -> session lookup -> answer
- Scenario B: Unverified parent asks for child data -> blocked
- Scenario C: Parent requests unrelated child ID -> denied (cross-account defense)
- Scenario D: Session unavailable -> ticket offered -> confirmation -> ticket created once
- Scenario E: Backend unavailable -> safe fallback
- Scenario F: Coach accesses assigned student -> allowed
- Scenario G: Coach accesses unassigned student -> denied
- Scenario H: Anonymous feedback -> saved
- Scenario I: Academy asks custom plan -> lead created
- Scenario J: Write action idempotency -> no duplicate action
- Scenario K: Session reset / cleanup isolation
- Required Voice Test Questions intent & grounding evaluation

Does NOT require Sarvam API credits.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "prototype"))

from tools import (
    CallerIdentity,
    CallerRole,
    PermissionService,
    SupportToolService,
    VerificationState,
)
from tools.account.mock import MockAccountBackend
from tools.intents import SupportIntent, detect_support_intent, extract_identifiers
from tools.grounding import format_tool_result_context, format_verification_required_context

FIXTURE_PATH = PROJECT_ROOT / "prototype" / "tests" / "fixtures" / "accounts.json"


def print_header(title: str):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def print_step(name: str, passed: bool, detail: str = ""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"[{status}] {name}")
    if detail:
        print(f"        {detail}")


async def run_checks() -> bool:
    all_passed = True
    print_header("PHASE 7 SUPPORT TOOLS & ACTIONS VERIFICATION")

    service = SupportToolService(
        session_id="check-sess-001",
        backend_mode="mock",
        fixture_path=str(FIXTURE_PATH),
        allow_mock_verification=True,
    )

    # -------------------------------------------------------------
    # Scenario A: Parent verifies -> child lookup -> session lookup
    # -------------------------------------------------------------
    print_header("Scenario A: Parent Verified Session Lookup")
    v = await service.verify_caller("ACC-P100")
    c1 = (v is True and service.caller.is_verified and service.caller.role == CallerRole.PARENT)
    print_step("Parent Verification (ACC-P100)", c1, f"Caller: {service.caller.name}, Role: {service.caller.role.value}")
    all_passed &= c1

    stu_res = await service.execute_tool("student.lookup", {"student_id": "STU-C001"})
    c2 = (stu_res.success and stu_res.data.name == "Aarav Sharma")
    print_step("Child Lookup (STU-C001)", c2, f"Student: {stu_res.data.name if stu_res.success else 'None'}")
    all_passed &= c2

    ses_res = await service.execute_tool("session.lookup", {"student_id": "STU-C001"})
    c3 = (ses_res.success and ses_res.data.status == "unavailable")
    print_step("Session Lookup (STU-C001)", c3, f"Status: {ses_res.data.status if ses_res.success else 'None'}, Reason: {ses_res.data.reason_if_unavailable}")
    all_passed &= c3

    # Grounding context check
    ctx = format_tool_result_context("session.lookup", ses_res, service.caller, "en-IN")
    c4 = ("status = unavailable" in ctx and "TOOL_RESULT:" in ctx)
    print_step("Grounded Response Context", c4, "Contains verified status and instructions")
    all_passed &= c4

    # -------------------------------------------------------------
    # Scenario B: Unverified parent asks for child data -> blocked
    # -------------------------------------------------------------
    print_header("Scenario B: Unverified Caller Blocked")
    unverified_service = SupportToolService(backend_mode="mock", fixture_path=str(FIXTURE_PATH))
    unverified_res = await unverified_service.execute_tool("session.lookup", {"student_id": "STU-C001"})
    c5 = (not unverified_res.success and unverified_res.error_code == "NOT_VERIFIED")
    print_step("Unverified Access Denied", c5, f"Error: {unverified_res.error_code}, Message: {unverified_res.safe_message}")
    all_passed &= c5

    # -------------------------------------------------------------
    # Scenario C: Parent requests unrelated child ID -> denied
    # -------------------------------------------------------------
    print_header("Scenario C: Cross-Account Access Denied")
    cross_res = await service.execute_tool("session.lookup", {"student_id": "STU-C002"})
    c6 = (not cross_res.success and cross_res.error_code == "NOT_AUTHORIZED")
    print_step("Cross-Account Denial (STU-C002 for Parent ACC-P100)", c6, f"Error: {cross_res.error_code}")
    all_passed &= c6

    # -------------------------------------------------------------
    # Scenario D: Session unavailable -> ticket confirmation -> ticket created once
    # -------------------------------------------------------------
    print_header("Scenario D: Ticket Confirmation & Creation")
    # Staging write action
    stage_res = await service.execute_tool(
        "ticket.create",
        {"summary": "Session unavailable for Aarav", "category": "session_issue"},
        idempotency_key="idem-key-live-1",
    )
    c7 = (stage_res.success and service.has_pending_action())
    print_step("Ticket Action Staged (Requires Confirmation)", c7)
    all_passed &= c7

    # Confirm
    ticket_res = await service.confirm_pending_action(True)
    c8 = (ticket_res and ticket_res.success and ticket_res.data.ticket_id.startswith("TCK-"))
    print_step("Ticket Confirmed & Created", c8, f"Ticket ID: {ticket_res.data.ticket_id if ticket_res else 'None'}")
    all_passed &= c8

    # Duplicate execution check
    dup_res = await service.execute_tool(
        "ticket.create",
        {"summary": "Session unavailable for Aarav"},
        idempotency_key="idem-key-live-1",
        skip_confirmation_check=True,
    )
    c9 = (dup_res.data.ticket_id == ticket_res.data.ticket_id)
    print_step("Idempotent Duplicate Prevention", c9, f"Same Ticket ID returned: {dup_res.data.ticket_id}")
    all_passed &= c9

    # -------------------------------------------------------------
    # Scenario E: Backend unavailable -> safe fallback
    # -------------------------------------------------------------
    print_header("Scenario E: Backend Unavailable Handling")
    failing_backend = MockAccountBackend(fixture_path=str(FIXTURE_PATH), simulate_failure=True)
    failing_service = SupportToolService(account_backend=failing_backend, backend_mode="mock")
    failing_service.caller.auth_state = VerificationState.VERIFIED
    failing_service.caller.role = CallerRole.PARENT
    failing_service.caller.children = ["STU-C001"]

    fail_res = await failing_service.execute_tool("session.lookup", {"student_id": "STU-C001"})
    c10 = (not fail_res.success and fail_res.error_code == "BACKEND_UNAVAILABLE")
    print_step("Graceful Backend Failure", c10, f"Safe message: {fail_res.safe_message}")
    all_passed &= c10

    # -------------------------------------------------------------
    # Scenario F: Coach accesses assigned student -> allowed
    # -------------------------------------------------------------
    print_header("Scenario F: Coach Access to Assigned Student")
    coach_service = SupportToolService(backend_mode="mock", fixture_path=str(FIXTURE_PATH))
    await coach_service.verify_caller("ACC-T001")
    coach_res = await coach_service.execute_tool("session.lookup", {"student_id": "STU-C001"})
    c11 = (coach_res.success and coach_res.data.student_id == "STU-C001")
    print_step("Coach Assigned Student Lookup", c11, f"Coach: {coach_service.caller.name}, Student: STU-C001")
    all_passed &= c11

    # -------------------------------------------------------------
    # Scenario G: Coach accesses unassigned student -> denied
    # -------------------------------------------------------------
    print_header("Scenario G: Coach Access to Unassigned Student Denied")
    unassigned_res = await coach_service.execute_tool("session.lookup", {"student_id": "STU-C002"})
    c12 = (not unassigned_res.success and unassigned_res.error_code == "NOT_AUTHORIZED")
    print_step("Unassigned Student Denial", c12, f"Error: {unassigned_res.error_code}")
    all_passed &= c12

    # -------------------------------------------------------------
    # Scenario H: Anonymous feedback -> saved
    # -------------------------------------------------------------
    print_header("Scenario H: Anonymous Feedback Capture")
    anon_service = SupportToolService(backend_mode="mock", fixture_path=str(FIXTURE_PATH))
    fb_res = await anon_service.execute_tool("feedback.create", {"text": "Great platform!", "category": "praise"})
    c13 = (fb_res.success and fb_res.data.feedback_id.startswith("FDB-"))
    print_step("Anonymous Feedback Saved", c13, f"Feedback ID: {fb_res.data.feedback_id if fb_res.success else 'None'}")
    all_passed &= c13

    # -------------------------------------------------------------
    # Scenario I: Academy asks custom plan -> lead created
    # -------------------------------------------------------------
    print_header("Scenario I: Academy / Custom Plan Lead Creation")
    lead_res = await service.execute_tool(
        "lead.create",
        {
            "lead_type": "academy",
            "organization_name": "Apex Chess Academy",
            "student_count": 80,
            "summary": "Inquiring about academy dashboard and bulk licenses",
        },
    )
    c14 = (lead_res.success and lead_res.data.lead_id.startswith("LED-"))
    print_step("Academy Lead Created", c14, f"Lead ID: {lead_res.data.lead_id if lead_res.success else 'None'}")
    all_passed &= c14

    # -------------------------------------------------------------
    # Scenario J: Caller interrupts during tool response -> no duplicate
    # -------------------------------------------------------------
    print_header("Scenario J: Write Idempotency on Interruption")
    idem_key = "interrupted-key-999"
    write1 = await service.execute_tool("callback.create", {"reason": "Callback request"}, idempotency_key=idem_key, skip_confirmation_check=True)
    write2 = await service.execute_tool("callback.create", {"reason": "Callback request"}, idempotency_key=idem_key, skip_confirmation_check=True)
    c15 = (write1.data.request_id == write2.data.request_id and len(service.support_backend.callbacks) == 1)
    print_step("No Duplicate Callback on Re-submission", c15, f"Callback ID: {write1.data.request_id}")
    all_passed &= c15

    # -------------------------------------------------------------
    # Scenario K: Session Isolation & Cleanup
    # -------------------------------------------------------------
    print_header("Scenario K: Session Isolation & Cleanup")
    service.reset()
    c16 = (not service.caller.is_verified and service.caller.role == CallerRole.UNKNOWN and len(service.idempotency_keys) == 0)
    print_step("Complete Session Context Reset", c16)
    all_passed &= c16

    # -------------------------------------------------------------
    # Required Voice Test Questions Intent Verification
    # -------------------------------------------------------------
    print_header("Required Voice Test Questions (Section 42)")
    voice_questions = [
        ("I'm a parent. My child cannot see today's session.", SupportIntent.SESSION_LOOKUP),
        ("Can you check my child's session?", SupportIntent.SESSION_LOOKUP),
        ("What plan is my account on?", SupportIntent.SUBSCRIPTION_LOOKUP),
        ("Can you create a support ticket?", SupportIntent.CREATE_TICKET),
        ("I want someone to call me back.", SupportIntent.CALLBACK_REQUEST),
        ("I want to give feedback.", SupportIntent.FEEDBACK),
        ("I run a chess academy and need a custom plan.", SupportIntent.CUSTOM_PLAN_LEAD),
        ("Can you transfer me to a human?", SupportIntent.HUMAN_ESCALATION),
    ]

    for q, expected in voice_questions:
        intent = detect_support_intent(q)
        ok = (intent == expected)
        print_step(f"'{q}'", ok, f"Detected: {intent.value} (Expected: {expected.value})")
        all_passed &= ok

    print_header(f"OVERALL SIMULATED TOOL RESULT: {'ALL PASS' if all_passed else 'FAIL'}")
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(run_checks())
    sys.exit(0 if success else 1)
