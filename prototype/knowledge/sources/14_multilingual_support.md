---
id: multilingual_support
topic: support
audience: general
verified: true
source_type: approved_internal
last_updated: 2026-09-22
provenance: agent prompt + Phase 4.1 implementation records
---
# Multilingual Support

## Languages the support line can converse in
The support line can converse in English, Hindi, Bengali, Tamil, Telugu, Kannada, Malayalam, Marathi, Gujarati, Punjabi and Odia. It also understands more Indian languages.

## STT understanding coverage
Sarvam STT supports many Indian languages and code-mixed speech. Coverage quality may vary by language, accent and background noise.

## LLM response capability
The LLM can reply in the requested or detected language, including Indian English, Hinglish and Tanglish code-mixing. It preserves natural code-switching rather than translating everything into plain English.

## TTS voice coverage
TTS voices are available for the supported languages through the Sarvam Bulbul v3 model. Voice quality and available speakers may vary by language.

## Fallback behaviour
If a language cannot be answered aloud, the system falls back according to the telephony configuration. The assistant should not claim a language is unavailable unless the system explicitly indicates it.
