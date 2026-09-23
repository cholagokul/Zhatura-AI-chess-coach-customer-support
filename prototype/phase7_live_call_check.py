"""Zhatura AI Customer Care — Phase 7 Simulated Exotel & Voice Agent Check (Section 51).

Tests the full voice loop logic:
    Phone-like audio/transcript → Phase 7 tool decision → mock backend
    → grounded voice answer → TTS synthesis / Exotel serializer.

Can run with:
    python prototype/phase7_live_call_check.py [--port 8001]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "prototype"))

import config
from agent.conversation import Conversation
from agent.voice_agent import VoiceAgent
from telephony.serializer import ExotelSerializer
from tools import CallerRole, SupportToolService
from tools.grounding import format_tool_result_context
from tools.intents import SupportIntent, detect_support_intent

logger = logging.getLogger("phase7.live_check")
FIXTURE_PATH = PROJECT_ROOT / "prototype" / "tests" / "fixtures" / "accounts.json"


class MockChatCompletion:
    def __init__(self, reply: str):
        self.reply = reply

    @property
    def choices(self):
        class Choice:
            def __init__(self, c):
                self.message = type("Msg", (), {"content": c})()
        return [Choice(self.reply)]


class MockSarvamClient:
    def __init__(self):
        self.calls = []

    class _Chat:
        def __init__(self, parent):
            self.parent = parent

        async def completions(self, model=None, messages=None, **kwargs):
            self.parent.calls.append(messages)
            # Find system instructions to generate realistic mock response
            sys_content = " ".join(m["content"] for m in messages if m["role"] == "system")
            user_content = [m["content"] for m in messages if m["role"] == "user"][-1]

            if "ACCOUNT_VERIFICATION_REQUIRED" in sys_content:
                reply = "I can help with that. Could you please provide your account ID or mobile number to verify?"
            elif "ACCOUNT_VERIFIED" in sys_content:
                reply = "Welcome Priya Sharma. Your account is verified. How can I help you today?"
            elif "TOOL_RESULT:" in sys_content and "status = unavailable" in sys_content:
                reply = "Your child's session is currently unavailable due to scheduled maintenance."
            elif "CONFIRMATION_REQUIRED" in sys_content:
                reply = "I can create a support ticket for this issue. Would you like me to do that?"
            elif "TOOL_RESULT:" in sys_content and "ticket_id = TCK-" in sys_content:
                reply = "Your support ticket TCK-1001 has been successfully created."
            elif "Reply in Tamil" in sys_content:
                reply = "உங்கள் கணக்கு விவரங்களை சரிபார்க்க முடிந்தது."
            else:
                reply = "Thank you for contacting Zhatura support."

            return MockChatCompletion(reply)

    @property
    def chat(self):
        return self._Chat(self)


async def run_simulated_voice_pipeline() -> bool:
    print("\n" + "=" * 60)
    print("PHASE 7 SIMULATED EXOTEL / VOICE AGENT PIPELINE CHECK")
    print("=" * 60)

    cfg = config.Config(
        sarvam_api_key="test-key",
        env_file_found=True,
        support_backend_mode="mock",
        accounts_fixture_path=str(FIXTURE_PATH),
    )

    client = MockSarvamClient()
    tool_service = SupportToolService(
        session_id="voice-check-001",
        backend_mode="mock",
        fixture_path=str(FIXTURE_PATH),
        allow_mock_verification=True,
    )

    agent = VoiceAgent(
        cfg=cfg,
        conversation=Conversation.from_prompt_file(max_turns=10),
        chat_client=client,
        tool_service=tool_service,
    )

    serializer = ExotelSerializer(exotel_sample_rate=16000)
    steps_ok = True

    # 1. Unverified session lookup
    print("\n--- Step 1: Unverified Session Lookup ---")
    u1 = "My child cannot see today's session."
    r1 = await agent.generate_reply(u1, "en-IN")
    c1 = "verify" in r1.lower()
    print(f"Caller: {u1}")
    print(f"Agent:  {r1}")
    print(f"Result: {'PASS' if c1 else 'FAIL'}")
    steps_ok &= c1

    # 2. Account verification
    print("\n--- Step 2: Account Verification ---")
    u2 = "My account ID is ACC-P100."
    r2 = await agent.generate_reply(u2, "en-IN")
    c2 = agent.tool_service.caller.is_verified and "verified" in r2.lower()
    print(f"Caller: {u2}")
    print(f"Agent:  {r2}")
    print(f"Result: {'PASS' if c2 else 'FAIL'} (Caller: {agent.tool_service.caller.name})")
    steps_ok &= c2

    # 3. Verified session lookup
    print("\n--- Step 3: Verified Session Lookup (Grounded Result) ---")
    u3 = "Can you check today's session now?"
    r3 = await agent.generate_reply(u3, "en-IN")
    c3 = "unavailable" in r3.lower() and "maintenance" in r3.lower()
    print(f"Caller: {u3}")
    print(f"Agent:  {r3}")
    print(f"Result: {'PASS' if c3 else 'FAIL'}")
    steps_ok &= c3

    # 4. Ticket creation with confirmation
    print("\n--- Step 4: Ticket Creation Trigger (Confirmation Required) ---")
    u4 = "Can you create a support ticket for this?"
    r4 = await agent.generate_reply(u4, "en-IN")
    c4 = agent.tool_service.has_pending_action() and "ticket" in r4.lower()
    print(f"Caller: {u4}")
    print(f"Agent:  {r4}")
    print(f"Result: {'PASS' if c4 else 'FAIL'}")
    steps_ok &= c4

    print("\n--- Step 5: Caller Confirms Ticket Creation ---")
    u5 = "Yes, please create it."
    r5 = await agent.generate_reply(u5, "en-IN")
    c5 = not agent.tool_service.has_pending_action() and "tck-" in r5.lower()
    print(f"Caller: {u5}")
    print(f"Agent:  {r5}")
    print(f"Result: {'PASS' if c5 else 'FAIL'}")
    steps_ok &= c5

    # 6. Multilingual tool answer (Tamil)
    print("\n--- Step 6: Multilingual Tool Answer (Tamil) ---")
    u6 = "சப்ஸ்கிரிப்ஷன் விவரங்களை சரிபார்க்கவும்"
    r6 = await agent.generate_reply(u6, "ta-IN", reply_language="ta-IN")
    c6 = bool(r6)
    print(f"Caller: {u6}")
    print(f"Agent:  {r6}")
    print(f"Result: {'PASS' if c6 else 'FAIL'}")
    steps_ok &= c6

    # 7. Exotel audio serializer check
    print("\n--- Step 7: Exotel Audio Serializer Check ---")
    dummy_pcm = b"\x00\x00" * 1600  # 100ms at 16000 Hz
    exotel_msgs = serializer.media_messages(dummy_pcm, src_rate=16000)
    c7 = len(exotel_msgs) > 0 and "media" in exotel_msgs[0]
    print(f"Serialized chunks: {len(exotel_msgs)}, first message sample: {exotel_msgs[0][:60]}...")
    print(f"Result: {'PASS' if c7 else 'FAIL'}")
    steps_ok &= c7

    # 8. End-call intent
    print("\n--- Step 8: End-Call Intent ---")
    u8 = "Cut the call."
    c8 = agent.is_ending(u8)
    print(f"Caller: {u8}")
    print(f"Is Ending: {c8}")
    print(f"Result: {'PASS' if c8 else 'FAIL'}")
    steps_ok &= c8

    print("\n" + "=" * 60)
    print(f"SIMULATED EXOTEL / VOICE AGENT RESULT: {'PASS' if steps_ok else 'FAIL'}")
    print("=" * 60)
    return steps_ok


if __name__ == "__main__":
    ok = asyncio.run(run_simulated_voice_pipeline())
    sys.exit(0 if ok else 1)
