"""Phase 3 tests — conversation memory, state machine, brand correction."""

import sys
from pathlib import Path

import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parent.parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

from agent.brand_correction import correct_brand_terms, matches_spoken_echo  # noqa: E402
from agent.conversation import Conversation  # noqa: E402
from agent.state import AgentState, AgentStateMachine, InvalidTransition  # noqa: E402


class TestConversation:
    def test_system_prompt_loads_from_file(self):
        conv = Conversation.from_prompt_file()
        assert "Zhatura" in conv.system_prompt

    def test_add_turns_and_messages(self):
        conv = Conversation("You are a helper.")
        conv.add_user("Hello")
        conv.add_assistant("Hi there")
        messages = conv.messages()
        assert messages[0] == {"role": "system", "content": "You are a helper."}
        assert messages[1] == {"role": "user", "content": "Hello"}
        assert messages[2] == {"role": "assistant", "content": "Hi there"}

    def test_empty_turns_ignored(self):
        conv = Conversation("sys")
        conv.add_user("   ")
        conv.add_assistant("")
        assert conv.messages() == [{"role": "system", "content": "sys"}]

    def test_history_trimmed_to_max_turns(self):
        conv = Conversation("sys", max_turns=2)
        for i in range(5):
            conv.add_user(f"u{i}")
            conv.add_assistant(f"a{i}")
        assert len(conv.turns) == 4  # 2 turns kept
        assert conv.turns[0]["content"] == "u3"

    def test_reset(self):
        conv = Conversation("sys")
        conv.add_user("hi")
        conv.reset()
        assert len(conv.messages()) == 1

    def test_empty_prompt_rejected(self):
        with pytest.raises(ValueError):
            Conversation("   ")

    def test_missing_prompt_file(self):
        with pytest.raises(FileNotFoundError):
            Conversation.from_prompt_file("/nonexistent/prompt.md")


class TestStateMachine:
    def test_normal_flow(self):
        sm = AgentStateMachine()
        assert sm.state is AgentState.IDLE
        sm.transition(AgentState.LISTENING)
        sm.transition(AgentState.PROCESSING)
        sm.transition(AgentState.SPEAKING)
        sm.transition(AgentState.LISTENING)

    def test_barge_in_flow(self):
        sm = AgentStateMachine(AgentState.SPEAKING)
        sm.transition(AgentState.INTERRUPTED)
        sm.transition(AgentState.LISTENING)

    def test_invalid_transition_raises(self):
        sm = AgentStateMachine(AgentState.IDLE)
        with pytest.raises(InvalidTransition):
            sm.transition(AgentState.INTERRUPTED)

    def test_stopping_is_terminal(self):
        sm = AgentStateMachine(AgentState.STOPPING)
        with pytest.raises(InvalidTransition):
            sm.transition(AgentState.LISTENING)

    def test_same_state_is_noop(self):
        sm = AgentStateMachine(AgentState.LISTENING)
        assert sm.transition(AgentState.LISTENING) is AgentState.LISTENING


class TestBrandCorrection:
    @pytest.mark.parametrize("variant", [
        "Jhatura", "Jathura", "Jatura", "JATURA", "Jatuara",
        "Zhathura", "zathura",
        # Indic-script variants observed live (Phase 3, 2026-09-21).
        "जतुरा", "झतूरा", "जंतुरा",
        "ஜெத்துரா", "ஜத்துரா", "ஜாத்துரா", "ஜதுரா",
        # Live-observed Phase 4.1/5: "Hedura" (real PSTN call) and
        # dropped-initial "atura" (saaras heard "What is atura?").
        "Hedura", "atura",
        # Telugu variants (Phase 5 multilingual call).
        "జతురా", "ఝతురా", "జాతురా", "ఝాతురా",
    ])
    def test_variants_become_zhatura(self, variant):
        assert "Zhatura" in correct_brand_terms(
            f"I need help with {variant}.")

    def test_word_boundary_safety(self):
        # "atura" must only match as a standalone word — longer words
        # ending in "atura" are never touched.
        text = "The Natura subscription is fine."
        assert correct_brand_terms(text) == text

    def test_correct_spelling_untouched(self):
        text = "I use Zhatura daily."
        assert correct_brand_terms(text) == text

    def test_unrelated_words_untouched(self):
        text = "My child cannot access the lesson."
        assert correct_brand_terms(text) == text

    def test_empty_text(self):
        assert correct_brand_terms("") == ""


class TestEchoSuppression:
    def test_echo_detected(self):
        spoken = "Please open your Parent Dashboard and check lessons"
        heard = "please open your parent dashboard and check"
        assert matches_spoken_echo(heard, spoken)

    def test_real_user_speech_not_echo(self):
        spoken = "Please open your Parent Dashboard."
        heard = "My child cannot access today's chess lesson."
        assert not matches_spoken_echo(heard, spoken)

    def test_empty_inputs(self):
        assert not matches_spoken_echo("", "hello")
        assert not matches_spoken_echo("hello", "")
