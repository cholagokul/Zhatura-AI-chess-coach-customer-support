# Phase 6 — Zhatura Knowledge Expansion + Real Support Validation

Date: 2026-09-22
Scope: expand the verified Zhatura knowledge base, validate all sources,
test retrieval and grounding across the wider corpus, and protect the
live Exotel + Sarvam pipeline.

## Status

**PARTIAL** — all code-side gates PASS. Final PASS is blocked by an
exhausted Sarvam account (HTTP 402 "No credits available") for both
simulated and real PSTN validation, and by the absence of additional
approved Zhatura product documents to close the remaining knowledge
gaps.

## Baseline

- Phase 5 final automated tests: **335/335 PASS**.
- Phase 6 automated tests after expansion: **370/370 PASS**.
- No regressions in Phase 4/4.1/5 code paths.

## Knowledge Sources Added

Expanded from 10 to **20 verified Markdown source files** under
`prototype/knowledge/sources/`:

1. `01_zhatura_overview.md`
2. `02_ai_chess_coach.md`
3. `03_student_features.md`
4. `04_parent_features.md`
5. `05_coach_features.md`
6. `06_academy_features.md`
7. `07_lessons_sessions.md`
8. `08_game_analysis.md`
9. `09_progress_tracking.md`
10. `10_puzzles_training.md`
11. `11_plans_pricing.md`
12. `12_account_login_help.md`
13. `13_technical_support.md`
14. `14_multilingual_support.md`
15. `15_faq.md`
16. `16_escalation_support.md`
17. `17_organization_custom_plans.md`
18. `18_privacy_security.md`
19. `19_supported_platforms.md`
20. `20_common_customer_issues.md`

## Knowledge Sources Updated

- All existing sources were migrated to the numbered naming scheme.
- Every source now carries `source_type` metadata
  (`approved_internal` by default; `approved_pricing` reserved for
  future verified pricing sheets).
- Every source keeps `verified: true`, `last_updated` and `provenance`.

## Total Verified Sources

**20** Markdown source files.

## Total Chunks

**95 verified chunks** (up from 24 in Phase 5).

## Knowledge Gaps

See [`KNOWLEDGE_GAPS.md`](KNOWLEDGE_GAPS.md). Major intentional gaps:

- Exact plans, prices, discounts, refunds, renewals, trials
- Lesson/session structure, duration, scheduling
- Detailed student/parent/coach dashboard contents
- Academy scale limits, admin roles, bulk pricing
- Game-analysis sources, mistake categories, review flow
- Puzzle library size, difficulty progression, scoring
- Password-reset URLs, account-creation flow, role switching
- Supported device/browser matrix and system requirements

No gap is filled with invented facts. Each gap is represented by a
`status: unavailable` chunk or by an explicit "not yet documented in
verified sources" section.

## Validation Results

```text
cd prototype && python -m knowledge.build_index
...
Documents   : 20
Chunks      : 95
Verified    : 95/95
VALIDATION: OK
```

Extended validator checks:

- all chunks verified
- no empty documents
- no duplicate IDs
- no duplicate content
- no missing topic/source/source_type
- no placeholder/test-fixture text leaks
- no unapproved pricing claims in `status=available` chunks

## Retrieval Architecture

Unchanged from Phase 5: pure-Python hybrid lexical retrieval,
in-memory, with synonym expansion, brand-token down-weighting,
phrase/topic/audience boosts and native-script hints.

## Retrieval Evaluation

Tested (§14) across: overview, AI Chess Coach, parent/student/coach
features, academies, lessons, sessions, game analysis, puzzles,
progress tracking, plans, pricing, account/login, unknown questions and
follow-up context. Correct source/topic retrieved in all targeted cases.

## Grounding

- HIGH/MEDIUM confidence → `VERIFIED ZHATURA KNOWLEDGE` context.
- LOW / unknown topics → mandatory honesty rule.
- Pricing queries → `pricing_unavailable` guard.
- Account-specific queries → `account_limited` guard (owner word +
  problem word).

## Plan / Pricing Safety

All plan/pricing/organization-plan chunks carry `status: unavailable`.
The pricing guard fires on every price/plan query and the context
contains no ₹, $, numbers or plan names.

## Account-Specific Safety

Account-specific detection requires both an ownership signal and a
problem/access signal. Bare "my child" stays grounded; "my child cannot
see today's lesson" triggers the account-limited guard.

## Parent / Student / Coach / Academy Knowledge

Each audience has a dedicated source file. Verified facts are limited to
what is in README/agent prompt/brand sentences; deeper details are
explicitly marked unavailable.

## Lessons / Sessions

Covered by `07_lessons_sessions.md`; detailed mechanics are unavailable.

## AI Chess Coach

Covered by `02_ai_chess_coach.md`; detailed coaching mechanics are
unavailable.

## Game Analysis

Covered by `08_game_analysis.md`; supported sources and recommendation
rules are unavailable.

## Multilingual Knowledge

Covered by `14_multilingual_support.md`; preserves the distinction
between STT understanding, LLM response and TTS voice coverage.

## Follow-Up Context

Tested: "What can parents see?" → "And coaches?" inherits topic and
retrieves coach features. Lesson context followed by an account-specific
follow-up still triggers the account guard.

## Unknown Answer Handling

Deliberately unsupported questions ("free laptops", "book flights")
return grounded overview context or unknown mode without inventing the
requested capability.

## Multilingual Retrieval

Native-script hints already handle ta/hi/te. The expanded corpus keeps
retrieval language-agnostic; no new heavy infrastructure added.

### English
PASS — retrieval and grounding verified.

### Hindi
PASS — native-script terms map to latin retrieval tokens.

### Tamil
PASS — including Tanglish code-mixed transcripts.

### Telugu
PASS — native-script coach/dashboard/chess terms resolved.

### Code-Mixed
PASS — Tanglish/Hinglish queries retrieve the correct audience/topic.

## Retrieval Latency

Measured over 1,050 calls (50 iterations × 21 queries) on this machine:

| Metric | Value |
|---|---|
| average | **0.198 ms** |
| median | 0.185 ms |
| p95 | 0.255 ms |
| max | 3.322 ms |

Well under the 200–300 ms target.

## Automated Tests

**370/370 PASS**:

- Phase 5 knowledge tests (66)
- Phase 6 knowledge tests (30)
- Phase 3 brand-correction + Phase 5 native-hint tests
- TTS HTTP-402 mapping test
- All prior regression suites (Phase 1–4.1)

## Golden Tests

19 golden cases in `prototype/tests/golden/knowledge_golden.json`:
mode, required concepts and forbidden claims all pass.

## Simulated Exotel/Sarvam Test

**BLOCKED** — Sarvam returns HTTP 402 `insufficient_quota_error`
("No credits available.") and the realtime STT WebSocket reports
"Credits exhausted". The same condition would affect any call on the
live :8000 server right now. No code-side failure.

To re-run once credits are available:

```bash
EXOTEL_WEBSOCKET_PORT=8001 python prototype/phase4_exotel_server.py
python prototype/phase5_knowledge_live_check.py
```

## Real PSTN Test

**PENDING** — requires (1) Sarvam credit top-up, (2) live :8000 server
restart to load the Phase 6 corpus, and (3) user-side dial-in. Per your
instruction I will not restart the live :8000 server automatically.

Suggested script (§30):

"What is Zhatura?" → "What does the AI Chess Coach do?" → "I am a
parent. What can I see?" → "Can I track my child's progress?" → "What
can coaches do?" → "Can academies use Zhatura?" → "How do lessons
work?" → "What plans do you offer?" → "How much does it cost?" → "My
child can't see today's lesson." → "Can you explain that in Tamil?"
→ switch back to English → barge-in once → "Cut the call."

## Barge-In Regression

No code changes to the audio/turn pipeline; retrieval is synchronous
and discarded with a cancelled turn. PASS by design.

## End Call

No code changes; voice end-call bypasses retrieval. PASS by design.

## Session Cleanup

No code changes to `telephony/session.py`. PASS by design.

## Known Limitations

1. Sarvam account is out of credits, blocking live validation.
2. The live :8000 server is still running pre-Phase-6 code; it needs a
   manual restart to load the 20-file corpus.
3. Many detailed product facts remain unavailable because approved
   Zhatura documents were not provided.

## Remaining Knowledge Gaps

Listed in [`KNOWLEDGE_GAPS.md`](KNOWLEDGE_GAPS.md). The honest
"unavailable" answers are themselves grounded.

## Ready for Phase 7?

**NO** — pending:

1. Sarvam credit top-up + simulated voice rerun + real PSTN call.
2. Manual restart of the live :8000 server to activate Phase 6
   knowledge.
3. Approved Zhatura product/pricing/support documents to close the
   documented knowledge gaps.
