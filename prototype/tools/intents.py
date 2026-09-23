"""Zhatura AI Customer Care — Tool Intent Routing (Phase 7).

Lightweight, deterministic intent detection for tool actions, account lookups,
confirmation flows, feedback, leads, and human escalation.
Multilingual support for English, Hindi, Tamil, and Telugu.
"""

from __future__ import annotations

import re
from enum import Enum

# Identifier regexes for test / dev synthetic accounts
_ACC_RE = re.compile(r"\b(ACC-[A-Z0-9]+)\b", re.IGNORECASE)
_STU_RE = re.compile(r"\b(STU-[A-Z0-9]+)\b", re.IGNORECASE)
_COA_RE = re.compile(r"\b(COA-[A-Z0-9]+)\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"\b(\+?91[-.\s]?)?([6-9]\d{4}[-.\s]?\d{5})\b")


class SupportIntent(str, Enum):
    GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
    ACCOUNT_LOOKUP = "ACCOUNT_LOOKUP"
    STUDENT_LOOKUP = "STUDENT_LOOKUP"
    SESSION_LOOKUP = "SESSION_LOOKUP"
    LESSON_LOOKUP = "LESSON_LOOKUP"
    SUBSCRIPTION_LOOKUP = "SUBSCRIPTION_LOOKUP"
    CREATE_TICKET = "CREATE_TICKET"
    CALLBACK_REQUEST = "CALLBACK_REQUEST"
    FEEDBACK = "FEEDBACK"
    ACADEMY_LEAD = "ACADEMY_LEAD"
    CUSTOM_PLAN_LEAD = "CUSTOM_PLAN_LEAD"
    HUMAN_ESCALATION = "HUMAN_ESCALATION"
    CONFIRMATION_YES = "CONFIRMATION_YES"
    CONFIRMATION_NO = "CONFIRMATION_NO"
    VERIFY_IDENTITY = "VERIFY_IDENTITY"
    END_CALL = "END_CALL"


# Confirmation words
_YES_WORDS = (
    "yes", "yeah", "yep", "sure", "please do", "confirm", "go ahead",
    "do it", "create it", "okay", "ok", "haan", "ha", "aam", "sari",
    "theek hai", "avunu", "sari pannunga", "ஆம்", "சரி", "हाँ", "हां",
    "ठीक है", "అవును", "సరే",
)

_NO_WORDS = (
    "no", "nope", "don't", "do not", "cancel", "stop", "never mind",
    "nahi", "nahin", "vendaam", "vendam", "oddu", "இல்லை", "வேண்டாம்",
    "नहीं", "मत करो", "కాదు", "వద్దు",
)

# Intent triggers
_TICKET_WORDS = (
    "ticket", "support ticket", "raise a ticket", "create a ticket",
    "open a ticket", "file a complaint", "log a ticket", "டிக்கெட்",
    "टिकट", "టికెట్",
)

_CALLBACK_WORDS = (
    "call me back", "callback", "call back", "someone call me",
    "schedule a callback", "schedule a call", "request a call",
    "திரும்ப அழைக்க", "கால் பேக்", "கால்பேக்", "कॉल बैक", "తిరిగి కాల్",
)

_FEEDBACK_WORDS = (
    "give feedback", "leave feedback", "want to give feedback",
    "share feedback", "feedback", "suggestion", "கருத்து",
    "फीडबैक", "सुझाव", "ఫీడ్‌బ్యాక్",
)

_ACADEMY_LEAD_WORDS = (
    "run an academy", "chess academy", "my academy", "our academy",
    "school plan", "coaching center", "அகாடமி", "एकादमी", "अकादमी",
    "అకాడమీ",
)

_CUSTOM_PLAN_WORDS = (
    "custom plan", "plan for 100 students", "plan for 50 students",
    "multiple students", "bulk students", "bulk pricing", "enterprise plan",
    "custom pricing", "many students", "100 students",
)

_HUMAN_WORDS = (
    "talk to a human", "transfer me to a human", "speak to a person",
    "real person", "human agent", "representative", "human support",
    "customer care agent", "transfer me", "connect to agent",
    "மனிதர்", "इंसान", "మనిషి",
)

_SESSION_WORDS = (
    "session", "lesson", "today's session", "todays session",
    "today's lesson", "todays lesson", "class", "cannot see session",
    "missing session", "check session", "check lesson", "check my child's session",
    "session unavailable", "செஷன்", "பாடம்", "सेशन", "पाठ",
)

_SUBSCRIPTION_WORDS = (
    "what plan", "my plan", "subscription status", "check subscription",
    "my subscription", "current plan", "subscription details",
    "renewal date", "சப்ஸ்கிரிப்ஷன்", "सब्सक्रिप्शन", "ప్లాన్",
)

_STUDENT_WORDS = (
    "my child", "my kid", "my son", "my daughter", "student profile",
    "check child", "child's profile", "குழந்தை", "बच्चा", "బిడ్డ",
)

_VERIFY_WORDS = (
    "verify", "verify my account", "authenticate", "here is my id",
    "my account id is", "account id", "my id is", "otp", "verify me",
)


def extract_identifiers(text: str) -> dict[str, str]:
    """Extract synthetic IDs or phone numbers from user speech."""
    found: dict[str, str] = {}
    m_acc = _ACC_RE.search(text)
    if m_acc:
        found["account_id"] = m_acc.group(1).upper()
    m_stu = _STU_RE.search(text)
    if m_stu:
        found["student_id"] = m_stu.group(1).upper()
    m_coa = _COA_RE.search(text)
    if m_coa:
        found["coach_id"] = m_coa.group(1).upper()
    m_ph = _PHONE_RE.search(text)
    if m_ph:
        found["phone"] = m_ph.group(0).replace(" ", "").replace("-", "")
    return found


def detect_support_intent(
    text: str,
    has_pending_confirmation: bool = False,
) -> SupportIntent:
    """Classify the caller utterance into a structured SupportIntent."""
    lowered = text.strip().lower().rstrip(".!?")

    # If an action confirmation is currently pending, check YES/NO first
    if has_pending_confirmation:
        for w in _YES_WORDS:
            if lowered == w or f" {w} " in f" {lowered} " or lowered.startswith(f"{w} "):
                return SupportIntent.CONFIRMATION_YES
        for w in _NO_WORDS:
            if lowered == w or f" {w} " in f" {lowered} " or lowered.startswith(f"{w} "):
                return SupportIntent.CONFIRMATION_NO

    # Explicit identity verification or credentials provided
    ids = extract_identifiers(text)
    if ids or any(w in lowered for w in _VERIFY_WORDS):
        return SupportIntent.VERIFY_IDENTITY

    # Support write actions
    if any(w in lowered for w in _TICKET_WORDS):
        return SupportIntent.CREATE_TICKET

    if any(w in lowered for w in _CALLBACK_WORDS):
        return SupportIntent.CALLBACK_REQUEST

    if any(w in lowered for w in _FEEDBACK_WORDS):
        return SupportIntent.FEEDBACK

    # Leads
    if any(w in lowered for w in _CUSTOM_PLAN_WORDS):
        return SupportIntent.CUSTOM_PLAN_LEAD

    if any(w in lowered for w in _ACADEMY_LEAD_WORDS):
        return SupportIntent.ACADEMY_LEAD

    # Escalation
    if any(w in lowered for w in _HUMAN_WORDS):
        return SupportIntent.HUMAN_ESCALATION

    # Lookups
    if any(w in lowered for w in _SESSION_WORDS) and (
        "my " in lowered or "child" in lowered or "kid" in lowered or "today" in lowered
    ):
        return SupportIntent.SESSION_LOOKUP

    if any(w in lowered for w in _SUBSCRIPTION_WORDS):
        return SupportIntent.SUBSCRIPTION_LOOKUP

    if any(w in lowered for w in _STUDENT_WORDS) and (
        "profile" in lowered or "detail" in lowered or "check" in lowered
    ):
        return SupportIntent.STUDENT_LOOKUP

    if "my account" in lowered and ("check" in lowered or "status" in lowered or "detail" in lowered):
        return SupportIntent.ACCOUNT_LOOKUP

    return SupportIntent.GENERAL_KNOWLEDGE
