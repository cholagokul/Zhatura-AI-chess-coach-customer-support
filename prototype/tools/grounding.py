"""Zhatura AI Customer Care — Tool Result Grounding (Phase 7).

Formats structured LLM system prompts for tool results, verification requirements,
confirmation gates, permission denials, and backend errors.
"""

from __future__ import annotations

from typing import Any

from .models import CallerIdentity, ToolResult


def format_verification_required_context(
    action_description: str,
    language: str = "en-IN",
) -> str:
    return (
        "ACCOUNT_VERIFICATION_REQUIRED:\n"
        f"The caller is requesting {action_description}, which requires access to account details. "
        "However, their account is currently UNVERIFIED.\n"
        "INSTRUCTION:\n"
        "Tell the caller politely that you can help with that, but you need to verify their account first. "
        "Ask them to provide their account ID or registered mobile number to verify. "
        "Do NOT disclose any private account, student, or session details. Keep it short (1–2 sentences)."
    )


def format_confirmation_required_context(
    action_name: str,
    action_details: str,
    language: str = "en-IN",
) -> str:
    return (
        "CONFIRMATION_REQUIRED:\n"
        f"Proposed write action: {action_name} ({action_details}).\n"
        "INSTRUCTION:\n"
        f"Ask the caller explicitly if they would like you to {action_name} for this. "
        "Do NOT perform the action until the caller confirms with 'yes' or equivalent agreement. "
        "Keep it short and conversational (1–2 sentences)."
    )


def format_permission_denied_context(
    target: str,
    reason: str = "caller role does not have authorization for this record",
    language: str = "en-IN",
) -> str:
    return (
        "TOOL_PERMISSION_DENIED:\n"
        f"Access to {target} was denied ({reason}).\n"
        "INSTRUCTION:\n"
        "Tell the caller politely that their verified account is not authorized to access these details. "
        "Offer to help with other permitted inquiries or connect them with support. Do NOT invent or leak details."
    )


def format_backend_unavailable_context(
    tool_name: str,
    language: str = "en-IN",
) -> str:
    return (
        "TOOL_BACKEND_UNAVAILABLE:\n"
        f"The system service for {tool_name} is temporarily offline or unavailable.\n"
        "INSTRUCTION:\n"
        "Tell the caller honestly that you cannot access the account system right now. "
        "Do NOT pretend you checked the account. Offer to take a support note or have someone follow up."
    )


def format_not_found_context(
    entity_name: str,
    query_param: str,
    language: str = "en-IN",
) -> str:
    return (
        "TOOL_NOT_FOUND:\n"
        f"No record found for {entity_name} ({query_param}).\n"
        "INSTRUCTION:\n"
        f"Inform the caller politely that no record was found for {entity_name}. "
        "Ask them to double check the details, and offer to help."
    )


def format_tool_result_context(
    tool_name: str,
    result: ToolResult,
    caller: CallerIdentity | None = None,
    language: str = "en-IN",
) -> str:
    """Format structured tool output into a grounded instruction block for the LLM."""
    if not result.success:
        if result.error_code == "NOT_VERIFIED":
            return format_verification_required_context(tool_name, language)
        if result.error_code == "NOT_AUTHORIZED":
            return format_permission_denied_context(tool_name, result.safe_message, language)
        if result.error_code in ("BACKEND_UNAVAILABLE", "BACKEND_NOT_CONFIGURED", "TIMEOUT"):
            return format_backend_unavailable_context(tool_name, language)
        if result.error_code == "NOT_FOUND":
            return format_not_found_context(tool_name, str(result.data), language)

    # Format successful data
    data_lines = []
    if isinstance(result.data, dict):
        for k, v in result.data.items():
            if v is not None:
                data_lines.append(f"{k} = {v}")
    elif hasattr(result.data, "__dict__"):
        for k, v in vars(result.data).items():
            if not k.startswith("_") and v is not None:
                data_lines.append(f"{k} = {v}")
    else:
        data_lines.append(f"data = {result.data}")

    formatted_data = "\n".join(data_lines)

    return (
        f"TOOL_RESULT:\n"
        f"tool = {tool_name}\n"
        f"verified = {result.verified}\n"
        f"source = {result.source}\n"
        f"RESULT_DATA:\n"
        f"{formatted_data}\n\n"
        "INSTRUCTION:\n"
        "Answer the caller based strictly and ONLY on the verified data in TOOL_RESULT above. "
        "Do NOT invent causes, dates, or details that are not present. "
        "Speak naturally in the caller's language, keeping it short (1–3 sentences)."
    )
