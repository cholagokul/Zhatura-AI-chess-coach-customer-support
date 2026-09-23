# Phase 2 Audio Sample Evaluation

Tested 2026-09-21 with live Sarvam API: TTS `bulbul:v3` (speaker
`shreya`, 24000 Hz WAV) → STT `saaras:v4` (mode `transcribe`).

STT results were produced programmatically. TTS audio quality was not
listened to by a human during this phase.

## TTS Generation

| Language | Samples | TTS Generated | Files Valid WAV | TTS Quality |
|---|---:|---:|---:|---|
| English (en-IN) | 5 | Yes | Yes | Manual listening review required |
| Tamil (ta-IN) | 3 | Yes | Yes | Manual listening review required |
| Hindi (hi-IN) | 3 | Yes | Yes | Manual listening review required |
| Hinglish (hi-IN voice) | 2 | Yes | Yes | Manual listening review required |
| Tanglish (ta-IN voice) | 2 | Yes | Yes | Manual listening review required |
| Terminology (en-IN) | 7 | Yes | Yes | Manual listening review required |

## STT Round-Trip Results (transcript accuracy)

| Language | Sample | STT Result | Brand Accuracy | Notes |
|---|---|---|---|---|
| English | welcome | Correct (except brand) | "Jathura" | Meaning fully preserved |
| English | account_help | Correct (except brand) | "JATURA" | |
| English | problem | Correct | n/a | Exact transcript |
| English | subscription | Correct | n/a | Exact transcript |
| English | human_transfer | Correct | n/a | "the human" article added; meaning intact |
| Tamil | welcome | Correct (except brand) | "ஜதுரா" | Native-script transcript |
| Tamil | account_help | Correct (except brand) | "ஜத்துரா" | |
| Tamil | problem | Correct | n/a | |
| Hindi | welcome | Correct (except brand) | "जतुरा" | |
| Hindi | account_help | Correct (except brand) | "झतोरा" | |
| Hindi | problem | Correct | n/a | |
| Hinglish | welcome | Correct (except brand) | "जतुरा" | Returned Devanagari script |
| Hinglish | account_help | Good | "जतुरा" | "account" → "काउंट"; Devanagari output |
| Tanglish | welcome | Good | "ஜாத்துரா" | Tamil script output; "வரவிருக்கிறோம்" ≈ "வரவேற்கிறோம்" |
| Tanglish | account_help | Correct (except brand) | "ஜதுரா" | |

## Zhatura Brand Recognition (terminology set, en-IN)

| Sample | Without keyterms | With keyterms | Brand Correct? |
|---|---|---|---|
| brand_zhatura | "Jhatura." | "Zhatura." | Only with keyterms |
| brand_zhatura_ai | "Jatura AI is a learning platform." | "Zhatura AI is a learning platform." | Only with keyterms |
| brand_chess_coach | "Jatuara AI chess coach." | "Zhatura AI chess coach." | Only with keyterms |
| brand_parent_dashboard | "…the parent dashboard." | "…the Parent Dashboard." | Only with keyterms |
| brand_coach_dashboard | "…the coach dashboard." | "…the Coach Dashboard." | Only with keyterms |
| brand_student_dashboard | "…the student dashboard." | "…the Student Dashboard." | Only with keyterms |
| brand_chess_academy | "…the Jhatura Chess Academy." | "…the Zhatura Chess Academy." | Only with keyterms |

**Conclusion:** Sarvam STT never recognizes "Zhatura" without help
(common mishearings: Jhatura, Jatura, Jathura, JATURA, ஜதுரா, जतुरा).
The `keyterms` parameter of `saaras:v4` fixes this 100% (7/7) in this
test set. **Phase 3+ must pass Zhatura keyterms on every STT call.**

Full raw transcripts: `transcripts/stt_results.json`.
