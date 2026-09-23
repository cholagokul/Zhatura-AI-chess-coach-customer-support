# Zhatura AI Chess Coach — Support Knowledge Expansion Plan

**Document ID**: `ZHAT-KNOW-PLAN-2026-09`  
**Classification**: Enterprise Knowledge Management & Support Operations  
**Operating Entity**: Namali Innovations Private Limited  
**Target Platform**: `/support` & Telephony AI Customer Care (`044-47615470`)  
**Status**: Approved Strategic Plan  

---

## 1. Vision & Strategic Objectives

The Zhatura Customer Support Knowledge Architecture provides a unified, single source of truth across all customer touchpoints:
1. **The Web Customer Support Portal (`/support`)**: Instant, accessible self-service for students, parents, coaches, and academies.
2. **The 24/7 AI Voice Customer Care Line (`044-47615470`)**: Real-time conversational support in 11 Indian languages.
3. **Escalation & Support Operations**: Standardized ticketing and follow-up workflows for Namali Innovations Private Limited.

This document establishes the editorial, pedagogical, technical, and compliance roadmap for systematically expanding and maintaining the knowledge repository from its initial 20 core topics into a comprehensive enterprise help ecosystem.

---

## 2. Knowledge Governance & Editorial Roles

| Role | Primary Responsibility | Approval Gate |
| :--- | :--- | :--- |
| **Product Leadership** | Defining official subscription packages, pricing, and feature releases | Required for all pricing, plans, and tier specifications |
| **Chess Pedagogy Lead** | Verifying chess terminology, coaching mechanics, rating progression, and curriculum | Required for AI Coach, Lessons, Puzzles, and Analysis |
| **Legal & Compliance Officer** | Verifying company registration, privacy statements, DPDP Act 2023 compliance, and refund policies | Required for Terms, Privacy, Escalation, and Corporate Data |
| **Support Operations Architect** | Maintaining YAML schemas, taxonomy, search indexing, and voicebot knowledge ingestion | Required for markdown frontmatter and test integration |

---

## 3. Phased Implementation Roadmap

```
  Q4 2026                       Q1 2027                       Q2 2027                       Q3 2027
  Phase 1: Commercial & SLAs    Phase 2: Pedagogical Guides   Phase 3: Academy Multi-Seat   Phase 4: Multilingual Pan-India
┌─────────────────────────────┐┌─────────────────────────────┐┌─────────────────────────────┐┌─────────────────────────────┐
│ • Publish verified pricing  ││ • Interactive lesson guides ││ • Multi-branch admin SOPs   ││ • Regional language portals │
│ • Refund & renewal policies ││ • PGN import workflows      ││ • Coach certification specs ││ • Dialect & accent tuning   │
│ • Operating hours & SLAs    ││ • Blunder analysis guide    ││ • Bulk billing agreements   ││ • Video walkthrough guides  │
└─────────────────────────────┘└─────────────────────────────┘└─────────────────────────────┘└─────────────────────────────┘
```

### Phase 1: Commercial, Financial & Legal Baseline (Target: 30 Days)
* **Objective**: Resolve the highest-volume customer questions (Pricing, Subscriptions, Refunds, Operating Hours).
* **Deliverables**:
  1. Author and verify `11_plans_pricing.md`:
     - Define Student Monthly (₹), Student Annual (₹), and Family Plan options.
     - Specify money-back guarantee window (e.g., 7-day or 14-day refund policy).
     - Document cancellation and auto-renewal protocols.
  2. Author and verify `16_escalation_support.md`:
     - Formalize support operating hours (e.g., 9:00 AM – 9:00 PM IST, Monday through Saturday).
     - Define SLA response targets: Tier-1 voice resolution (immediate), Tier-2 callback (within 4 hours).
  3. Formalize privacy and child safety compliance statement in `18_privacy_security.md` pursuant to the Digital Personal Data Protection (DPDP) Act 2023.

### Phase 2: Pedagogical & Feature Deep Dives (Target: 60 Days)
* **Objective**: Provide detailed step-by-step visual and written guides for platform users.
* **Deliverables**:
  1. Detailed Student Dashboard manual (`03_student_features.md`):
     - Interactive puzzle modes, daily workout routines, and rating leaderboards.
  2. Comprehensive Parent Dashboard walkthrough (`04_parent_features.md`):
     - Reading child accuracy graphs, setting practice schedules, and managing email digests.
  3. AI Chess Coach pedagogical explanation (`02_ai_chess_coach.md`):
     - How the coach identifies candidate moves, explains tactics, and recommends positional concepts.

### Phase 3: Institutional & Academy Solutions (Target: 90 Days)
* **Objective**: Empower chess academies, schools, and private tutors to scale with Zhatura.
* **Deliverables**:
  1. Academy Onboarding & Administrative Manual (`06_academy_features.md`):
     - Provisioning bulk student accounts via CSV import.
     - Assigning head coaches and assistant instructors to specific student batches.
  2. Enterprise & School Pricing Framework (`17_organization_custom_plans.md`):
     - Tiered licensing for 50+, 200+, and 1,000+ student organizations.
     - GST invoice handling, purchase orders, and payment terms.

### Phase 4: Multilingual & Localized Knowledge (Target: 120 Days)
* **Objective**: Broaden accessibility across all 11 supported Indian languages.
* **Deliverables**:
  1. Localized UI guides in Hindi, Tamil, Telugu, Bengali, Kannada, Malayalam, Marathi, Gujarati, Punjabi, and Odia.
  2. Multilingual chess glossary (e.g., translating chess piece names, tactic concepts like "fork", "pin", "checkmate" into regional languages).
  3. Audio-assisted knowledge bites for accessibility.

---

## 4. Authoring & Verification Standard Operating Procedure (SOP)

Every knowledge document must strictly adhere to the Zhatura Knowledge Schema:

```markdown
---
id: [unique_snake_case_id]
topic: [overview | ai_coach | features | lessons | game_analysis | progress | puzzles | plans | account_help | support | faq]
audience: [general | student | child | parent | coach | academy | organization]
verified: [true | false]
status: [available | unavailable]
source_type: [approved_internal | legal_registry | product_spec]
last_updated: YYYY-MM-DD
provenance: [Source documents or approved leadership decisions]
---
# [Clear Document Title]

## [Section 1 Heading]
[Verified concise facts...]

## [Section 2 Heading]
[Verified facts or explicit CONTENT_REQUIRED marker if pending...]
```

### Mandatory Verification Checklist Before Publishing:
1. **Truthfulness Test**: Is every claim corroborated by an approved product spec or legal document?
2. **Zero Inventions**: Are any unverified pricing numbers, features, or deadlines present? (If yes, replace with `CONTENT_REQUIRED`).
3. **Security Audit**: Does the document contain any API keys, telephony credentials, internal IP addresses, or telephony vendor names? (Strictly forbidden).
4. **Automated Testing**: Run `./.venv/bin/pytest prototype/tests/test_support_website.py` to ensure schema validation passes.
5. **Audience Clarity**: Is the language tailored to the targeted reader (child-safe, parent-friendly, coach-actionable)?

---

## 5. Continuous Improvement & Analytics Loop

1. **Search Query Analysis**:
   - Collect client-side search terms that yielded 0 results from `/support` to identify emerging content demands.
2. **Voice Call Trend Monitoring**:
   - Aggregate categorized call summaries from the Exotel voice service (`044-47615470`) to detect recurring pain points.
3. **Weekly Knowledge Refinement**:
   - Update FAQs weekly based on real incoming parent and coach inquiries.
