"""Zhatura AI Customer Care — intent / topic / audience detection
(Phase 5).

Lightweight, deterministic classification before retrieval. No ML:
keyword tables with Indian-language hints, because voice callers use
English loanwords ("plan", "dashboard", "coach") even inside Hindi or
Tamil sentences.
"""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-zA-Z']+", re.IGNORECASE)

# topic → trigger words (English + common Indian-language forms)
_TOPIC_KEYWORDS = {
    "overview": ("zhatura", "company", "platform", "about",
                 "क्या है", "ज़तुरा", "என்ன", "ஸ்துரா"),
    "ai_coach": ("ai chess coach", "chess coach", "ai coach", "coach ai",
                 "coaching", "कोच", "கோச்"),
    "features": ("feature", "features", "what can", "do in zhatura",
                 "capabilities", "use zhatura", "फीचर"),
    "plans": ("plan", "plans", "package", "packages", "subscription",
              "pricing", "price", "cost", "fee", "fees", "discount",
              "refund", "renewal", "trial", "payment", "pay",
              "कीमत", "प्लान", "पैकेज", "सब्सक्रिप्शन", "कितना",
              "கட்டணம்", "பிளான்", "சப்ஸ்கிரிப்ஷன்", "விலை", "ధర",
              "ప్లాన్", "సబ్స్క్రిప్షన్"),
    "lessons": ("lesson", "lessons", "class", "classes", "session",
                "sessions", "पाठ", "क्लास", "पாடம்", "செஷன்"),
    "dashboard": ("dashboard", "डैशबोर्ड", "டாஷ்போர்டு", "డ్యాష్‌బోర్డ్"),
    "progress": ("progress", "track", "tracking", "improvement",
                 "report", "प्रोग्रेस", "प्रगति", "முன்னேற்றம்",
                 "புரொக்ரஸ்", "పురోగతి"),
    "puzzles": ("puzzle", "puzzles", "पज़ल", "பஸில்"),
    "game_analysis": ("game analysis", "analysis", "analyse", "review",
                      "game review", "विश्लेषण", "அணாலிசிஸ்"),
    "account_help": ("account", "login", "log in", "sign in", "password",
                     "cannot access", "can't access", "cannot see",
                     "can't see", "not working", "अकाउंट", "लॉगिन",
                     "அக்கவுண்ட்", "லாகின்", "అకౌంట్", "లాగిన్"),
    "support": ("support", "help", "human", "agent", "representative",
                "escalate", "complaint", "सपोर्ट", "मदद", "சப்போர்ட்",
                "உதவி"),
    "faq": ("faq", "question"),
}

_AUDIENCE_KEYWORDS = {
    "parent": ("parent", "father", "mother", "mom", "dad", "my child",
               "my kid", "my son", "my daughter", "माता", "पिता",
               "बच्चे", "बच्चा", "अम्मா", "அப்பா", "குழந்தை", "పేరెంట్",
               "నా బిడ్డ"),
    "academy": ("academy", "academies", "school", "organization",
                "organisation", "institute", "multiple students",
                "एकादमी", "अकादमी", "அகாடமி", "అకాడమీ"),
    # checked last among role words: "I run an academy with many
    # students" is an academy caller, not a student caller
    "student": ("student", "i am learning", "i learn", "विद्यार्थी",
                "मாணவர்", "విద్యార్థి"),
    "child": ("child", "kid", "kids", "children", "son", "daughter",
              "बच्चे", "बच्चा", "குழந்தை", "பிள்ளை", "పిల్లలు"),
    "coach": ("coach", "trainer", "teacher", "i teach", "कोच",
              "ट्रेनर", "பயிற்சியாளர்", "కోచ్"),
}

_PRICING_WORDS = (
    "price", "pricing", "cost", "fee", "fees", "plan", "plans",
    "package", "subscription", "discount", "refund", "renewal", "renew",
    "trial", "payment", "pay", "charge", "how much", "कीमत", "कितना",
    "प्लान", "पैकेज", "सब्सक्रिप्शन", "रिफंड", "கட்டணம்", "விலை",
    "எவ்வளவு", "ప్లాన்", "ధర", "ఎంత",
)

# Account-specific = ownership signal AND problem/access signal. A bare
# "my child" ("What can I see about my child's progress?") is a GENERAL
# parent question and must stay grounded; only "my child CANNOT see
# today's lesson"-style turns are account-specific (§24).
_ACCOUNT_OWNER_WORDS = (
    "my account", "my child", "my kid", "my son", "my daughter",
    "my subscription", "my payment", "my plan", "my login",
    "our account", "मेरा अकाउंट", "मेरे बच्चे", "என் குழந்தை",
    "నా ఖాతా", "నా బిడ్డ",
)
_ACCOUNT_PROBLEM_WORDS = (
    "cannot see", "can't see", "cannot access", "can't access",
    "cannot login", "can't login", "cannot log in", "can't log in",
    "not showing", "not working", "unable to", "not opening",
    "today's lesson", "today's session", "todays lesson",
    "todays session", "charged", "deducted", "didn't renew",
    "did not renew", "नहीं दिख", "नहीं खुल", "లॉगिन్ కావడం లేదు",
    "காணவில்லை", "திறக்கவில்லை",
)

# Turns that never need retrieval: greetings, thanks, acknowledgements.
_TRIVIAL_PATTERNS = (
    "hello", "hi", "hey", "namaste", "vanakkam", "good morning",
    "good afternoon", "good evening", "thank you", "thanks", "ok",
    "okay", "fine", "great", "yes", "no", "sure", "hmm", "bye",
    "नमस्ते", "धन्यवाद", "शुक्रिया", "ठीक", "वணक्कम्", "நன்றி",
    "சரி", "नमस्कार", "हाँ", "हां",
)


def _latin_words(text: str) -> list:
    return _WORD_RE.findall(text.lower())


def _contains_any(text: str, needles) -> bool:
    lowered = text.lower()
    return any(n in lowered for n in needles)


def detect_topic(text: str) -> "str | None":
    """Best-matching topic for a transcript fragment, else None."""
    lowered = text.lower()
    best, best_hits = None, 0
    for topic, words in _TOPIC_KEYWORDS.items():
        hits = sum(1 for w in words if w in lowered)
        if hits > best_hits:
            best, best_hits = topic, hits
    return best


def detect_audience(text: str) -> "str | None":
    lowered = text.lower()
    for audience, words in _AUDIENCE_KEYWORDS.items():
        if any(w in lowered for w in words):
            return audience
    return None


def is_pricing_query(text: str) -> bool:
    return _contains_any(text, _PRICING_WORDS)


def is_account_specific(text: str) -> bool:
    """Caller is asking about THEIR account/child/session with a problem
    or access signal — never pretend to look it up. A plain "my child"
    mention without a problem signal is just a parent question."""
    lowered = text.lower()
    return (_contains_any(lowered, _ACCOUNT_OWNER_WORDS)
            and _contains_any(lowered, _ACCOUNT_PROBLEM_WORDS))


def needs_knowledge(text: str, word_threshold: int = 2) -> bool:
    """True when this turn warrants a knowledge lookup.

    False for greetings/thanks/acks and very short turns with no topic
    signal (language-switch and end-call turns are already intercepted
    by the pipeline before this is ever consulted).
    """
    lowered = text.strip().lower().rstrip(".!?")
    if not lowered:
        return False
    if detect_topic(lowered) or detect_audience(lowered) or (
            is_pricing_query(lowered)):
        return True
    if len(_latin_words(lowered)) <= word_threshold and (
            _contains_any(lowered, _TRIVIAL_PATTERNS)):
        return False
    if any(lowered == p for p in _TRIVIAL_PATTERNS):
        return False
    # Question-shaped turns default to a lookup attempt: retrieval is
    # cheap, and a LOW confidence falls back safely.
    return ("?" in text or len(_latin_words(lowered)) >= 4
            or any(w in lowered for w in ("what", "how", "why", "can",
                                          "does", "do you", "बताओ",
                                          "क्या", "என்ன", "ఏమిటి")))
