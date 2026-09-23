# Phase 5 — Zhatura Knowledge Base Report

Date: 2026-09-22
Scope: grounded customer-support answers from verified Zhatura knowledge
only. The running Phase 4/4.1 Exotel server (port 8000) was never
stopped, restarted or modified at runtime; all live verification ran
against a dev instance on port 8001.

## Status

PARTIAL — all code-side gates PASS (see below); final PASS requires the
user-side real PSTN run (Phase 4 rule: "Do not fake the phone test").

## Baseline Regression

Baseline before Phase 5 work: 261 passed / 0 failed (recorded).
After: **326 passed / 0 failed** (65 new Phase 5 tests). The Phase 4
stabilization live check was re-run against the dev server code and
passed; the Phase 4.1 multilingual live check passed unchanged on the
live server earlier this session (its code paths are untouched —
`session.py` has zero Phase 5 edits).

## Knowledge Architecture

`prototype/knowledge/` (new package):

| Module | Role |
|---|---|
| `models.py` | `KnowledgeChunk` (id/title/topic/audience/content/source/section/verified/tags/status/…), `RetrievalHit`, `KnowledgeAnswer`, `Confidence`, `AnswerMode` |
| `intents.py` | deterministic topic/audience detection (EN + hi/ta/te hints), pricing & account-specific guards, `needs_knowledge` gate |
| `loader.py` | Markdown (meta block + per-section chunks), JSON, plain text |
| `store.py` | in-memory store with duplicate-id protection |
| `retriever.py` | hybrid lexical retrieval: weighted token overlap (brand tokens down-weighted, synonyms expanded) + title bonus + phrase boost + topic/audience filtering |
| `grounding.py` | confidence thresholds + mandatory honesty statements (unknown / pricing / account) |
| `formatter.py` | grounded system-message context; log-only source refs |
| `service.py` | `KnowledgeService.answer_with_knowledge()` facade + follow-up topic inheritance + §21 debug logs |
| `validate.py` | corpus validator |
| `build_index.py` | `python -m knowledge.build_index` CLI |

VoiceAgent (one added seam in `generate_reply`): knowledge context is
injected as a system message placed BEFORE the per-turn language
suffix, so Phase 4.1 reply-language routing is untouched.

## Trusted Sources

Verified-fact rule applied literally: the master plan document in
`docs/` is still a **placeholder** (the approved plan was never
placed), so the only genuinely verified Zhatura facts available are
those stated in this repo's README, the system prompt, and the brand
sentence set (`audio_samples/sentences.md`). Sources therefore cover:

- Zhatura is an AI-powered chess learning platform (audiences:
  students, children, parents, coaches, academies, organizations)
- Zhatura AI Chess Coach exists; children use it
- Student Dashboard (students log in), Parent Dashboard (parents view
  progress), Coach Dashboard (coaches manage batches)
- "Zhatura Chess Academy" offering name; academies are a served audience
- Support behaviour: no account access this phase; human-transfer
  acknowledgement; privacy rules
- Plans/pricing and lesson/session mechanics: explicit verified
  `status: unavailable` entries

Every source file carries `verified: true`, `last_updated`, and a
`provenance` line naming where the facts came from.

## Knowledge Files

10 documents, 24 chunks, 100% verified — `cd prototype && python -m
knowledge.build_index` output (VALIDATION: OK):
`zhatura_overview.md`, `ai_chess_coach.md`, `student_features.md`,
`parent_features.md`, `coach_features.md`, `academy_features.md`,
`plans.md` (status: unavailable), `lessons_sessions.md` (status:
unavailable), `faq.md`, `support.md`.

## Chunking Strategy

Semantic per-section chunks (`##`/`###` headings → one chunk each);
doc-level H1 without a body is dropped; chunks under 30 chars are
merged upward; every chunk inherits the doc's meta block and records
its section. Resulting chunks are all in the intended few-hundred-token
band with no arbitrary splitting.

## Retrieval Strategy

Hybrid lexical, pure Python, in-memory: weighted token overlap with
query-side synonym expansion ("kid→child", "cost→price/plan", "class→
lesson/session", …), brand tokens (`zhatura`, `chess`) down-weighted to
0.2 (they appear everywhere), exact-phrase boosts ("ai chess coach",
"parent dashboard", …), informative-token title bonus (+1.0), exact
question-title match (+2.0, FAQ), topic boost (+0.9) and audience boost
(+0.5). Verified chunks only; "unavailable" chunks rank normally so
honest gaps are groundable. No FAISS/Chroma: at 24 chunks an external
vector index adds nothing but dependencies.

## Topic Detection

Deterministic keyword tables per topic (overview, ai_coach, features,
plans, lessons, dashboard, progress, puzzles, game_analysis,
account_help, support, faq) with Hindi/Tamil/Telugu native-script and
transliteration hints (voice callers use English loanwords anyway).

## Audience Detection

general / parent / child / student / coach / academy(=organization),
checked parent → academy → student → child → coach ("academy with many
students" resolves to academy, not student). Follow-up turns inherit
topic+audience from the previous user turn when they carry none
("And coaches?" follows "What does the parent dashboard show?").

## Grounding Rules

- HIGH/MEDIUM confidence → `VERIFIED ZHATURA KNOWLEDGE` context block +
  voice-first rules ("answer ONLY from this, 1–3 sentences").
- LOW → `UNKNOWN_STATEMENT` mandatory rule (admit no verified info,
  offer other help, never guess).
- Pricing questions with no verified plan data → `pricing_unavailable`
  mode + `PRICING_UNAVAILABLE_STATEMENT` (wins over retrieval quality;
  wins only if the account guard doesn't).
- Account-specific (owner word + problem/access word) →
  `account_limited` + `ACCOUNT_LIMIT_STATEMENT`.
- Trivial turns, explicit language-switch requests and end-call phrases
  never trigger retrieval.

## Hallucination Prevention

Three independent layers: (1) honesty modes return mandatory
instructions, not open prompts; (2) system prompt §15 rules ("Never
invent prices/plans/…/account status; if no context is supplied, say
so and stop"); (3) validator + golden tests pin the behaviour.

## Plan / Pricing Safety

`plans.md` is a verified "no plan data" statement. Golden cases assert
the pricing guard fires for "What plans do you offer?", "How much does
Zhatura cost?" and free-trial/discount questions, and that the context
contains no ₹/$/per-month figures. The validator separately flags any
future plan chunk carrying numeric claims for manual review.

## Account-Specific Safety

Two-signal detection (ownership word × problem word) — a bare "my
child" in a general parent question stays fully grounded, while "My
child cannot see today's lesson" gets general info (if any) plus the
mandatory no-account-access statement and a support next step.

## Multilingual Knowledge Answers

Retrieval is English-internal (transcripts carry English loanwords for
product terms; native hints in intent tables); answers are produced by
the LLM in the caller's current language — the Phase 4.1
`detected/requested/reply/tts_language` routing is byte-identical.
Live: Tamil, Hindi, Telugu grounded answers and one Tanglish
code-mixed turn — see "Simulated Voice Test".

## Follow-Up Questions

`answer_with_knowledge(query, context_turns=…)` inherits topic/audience
from the most recent user turn when the follow-up carries none, and
enriches the retrieval query with the inherited topic; only the last 4
turns are inspected — the lifetime transcript is never used.

## Voice Integration

One integration point: `VoiceAgent.generate_reply` calls
`_knowledge_context()` (disabled via `KNOWLEDGE_ENABLED=false`, custom
corpus via `KNOWLEDGE_DIR`). Greetings/thanks/switch/end-call bypass.
`session.py` is untouched.

## Retrieval Latency

Measured directly on this machine (2026-09-22) over 500 calls to
`KnowledgeService.answer_with_knowledge()` covering English, Telugu,
Tanglish, pricing-guard and account-guard queries:

| Metric | Value |
|---|---|
| average | **0.067 ms** |
| median | 0.066 ms |
| p95 | 0.081 ms |
| max | 0.093 ms |

≈3000× under the 200–300 ms target (§32). Pure-Python in-memory
retrieval adds no perceptible turn latency. Per-turn `RETRIEVAL
LATENCY: N ms` log lines accompany every live query.

## Barge-In Regression

Retrieval is synchronous and in-memory — a cancelled turn discards the
retrieval result with it. Live barge-in check: see Simulated Voice
Test, Call C.

## End-Call Regression

Voice end-call bypasses retrieval and closes the call
(`user_end_phrase`, WSS close) — see Simulated Voice Test, Call A.

## Automated Tests

335 passed / 0 failed total; 66 new Phase 5 tests in
`prototype/tests/test_phase5_knowledge.py` (loading/parsing/metadata,
validator incl. duplicate detection and suspicious-pricing flag,
topic/audience/guards, retrieval ranking, native-script hint retrieval,
brand-mishearing → retrieval, golden set, VoiceAgent integration,
fixture isolation) plus brand-correction coverage in
`test_phase3_agent.py` (live-observed variants "Hedura", dropped-initial
"atura" with word-boundary safety, Telugu variants) and an HTTP-402
quota-exhausted error-mapping test in `test_tts.py`.

## Golden Tests

`prototype/tests/golden/knowledge_golden.json` — 14 cases with expected
mode, required context concepts and forbidden claims (incl. "no price
figures" for every pricing case, "not yet documented" for the
10,000-students scale question, "skipped" for greetings).

## Simulated Voice Test

(real Sarvam, simulated Exotel, dev server :8001 —
`python prototype/phase5_knowledge_live_check.py`)

**First run (16/19 PASS):** grounded English answers (Zhatura overview,
AI Chess Coach, parent dashboard), pricing guard voiced verbatim ("I
don't currently have verified details about our plans or pricing. I
won't guess or make anything u…" — no figures), account guard ("I
cannot see your child's account or today's lesson status from here…"),
Tamil/Hindi/Telugu grounded answers in native script with correct
per-language TTS, barge-in `clear` event, `active_calls` returns to 0
after every call. Three failures, all diagnosed and fixed:

| Failure | Root cause | Fix |
|---|---|---|
| "What is Zhatura?" answered as unknown | saaras misheard it as "What is atura?" — dropped-initial brand variant | brand variants += `atura` (word-boundary safe), `hedura` (seen on the real Phase 4.1 PSTN call), Telugu `జతురా/ఝతురా/జాతురా/ఝాతురా` |
| Tanglish parent-dashboard question answered as unknown | saaras transcribed the code-mixed question in pure Tamil script → zero latin tokens → empty retrieval set | `_NATIVE_HINTS` map (ta/hi/te script → latin retrieval tokens) incl. the observed "డేஷ்போர்டில்" dashboard form |
| voice end-call reported as failed | checker bug — read `end_reason`; call logs record `disconnect_reason` | checker fixed (the end-call itself worked: `user_end_phrase`, WSS closed) |

**Final rerun (2026-09-22, ~12:38 UTC): BLOCKED — Sarvam account has
no credits.** The Sarvam API returns HTTP 402
`insufficient_quota_error` ("No credits available.") on TTS and
"Credits exhausted" on the realtime STT WebSocket; the check aborts at
the call-A greeting ("no greeting audio in 15 s"). This is an
account-side condition, not a code regression — the same errors would
affect the live :8000 server for any call right now.

Incidental improvement while diagnosing: HTTP 402 is now mapped to a
clear "quota exhausted — top up the Sarvam subscription" error text in
`speech/tts.py`, `speech/stt.py`, `speech/streaming_tts.py` and
`speech/realtime_stt.py` (previously surfaced as a misleading
"network/connectivity failure").

**Action for you:** top up the Sarvam account, then tell me to re-run
`phase5_knowledge_live_check.py` — the dev server (:8001) is already
running with the final code, and the question audio is cached, so the
rerun takes only minutes.

## Real PSTN Test

PENDING — user-side script (report §39): "Hi, what is Zhatura?" →
"What does the AI Chess Coach do?" → "I am a parent. What can I see?" →
"What can coaches do?" → "What plans do you offer?" (expect honest
unavailable, no numbers) → "My child cannot see today's session."
(expect no-account statement) → "Can you explain that in Tamil?" →
"Cut the call."

**Note:** the running :8000 server loaded its code before Phase 5 was
written, so knowledge grounding activates on your next server restart.
Per your instruction I did not restart it. When you are ready:
stop the server, start it again as before — no other change is needed
(same port, same ngrok, same Exotel flow).

## Known Knowledge Gaps

By design (no verified sources exist yet): all plans/packages/pricing/
discounts/trials, lesson & session mechanics, detailed student/parent/
coach dashboard contents, puzzles & game-analysis specifics, academy
scale limits, login troubleshooting steps. **Action for you:** place
the approved Zhatura documents (product/plan/FAQ docs) into
`prototype/knowledge/sources/` — the honest gaps become grounded
answers the moment verified content exists.

## Remaining Issues

None code-side at time of writing. One environment blocker: the Sarvam
account is out of credits (HTTP 402) — the final simulated-voice rerun
(3 checks, all previously diagnosed and fixed in code/checker) is
queued behind that top-up.

## Ready for Phase 6?

NO — pending (1) Sarvam credit top-up + the blocked simulated rerun,
(2) your real PSTN voice test, and (3) approved Zhatura knowledge
documents to replace the explicit gap entries.
