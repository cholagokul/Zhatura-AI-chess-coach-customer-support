# Zhatura AI Chess Coach — Support Content Gaps & Requirements Inventory

**Document ID**: `ZHAT-GAP-2026-09`  
**Classification**: Enterprise Knowledge Operations / Content Strategy  
**Operating Entity**: Namali Innovations Private Limited  
**Public Support Line**: `095-138-86363`  
**Status**: Active Audit Reference  

---

## 1. Executive Summary & Content Discipline Mandate

Zhatura (`Zhatura AI Chess Coach`) is an AI-powered chess learning platform built for students, parents, chess coaches, and chess academies. Because customer trust—especially from parents of young learners, academy administrators, and educational institutions—is paramount, **Zhatura enforces an absolute zero-hallucination policy**.

Where exact pricing figures, technical specifications, or administrative dashboard mechanics have not been formally approved by product leadership, the system strictly marks these items as **`CONTENT_REQUIRED`**. Neither the AI voice support line (`095-138-86363`) nor the customer support portal (`/support`) will invent prices, subscription tiers, trial lengths, or unverified platform features. Instead, users are given verified high-level guidance and directed to Customer Support.

This document provides a systematic gap analysis across all 20 verified knowledge categories to guide future content authoring.

---

## 2. Comprehensive Inventory of Content Gaps by Knowledge Area

### Topic 01: Platform Overview & Brand Positioning (`01_zhatura_overview.md`)
* **Verified Elements**: AI-powered chess learning platform for students, children, parents, coaches, and academies. Features dedicated Student, Parent, and Coach dashboards.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Official certification or accreditation status (e.g., FIDE-aligned curriculum, national federation affiliations).
  - Clear boundary definitions between free platform access vs. paid institutional features.
  - Official minimum student age recommendations (e.g., ages 5+, 8+).

### Topic 02: AI Chess Coach Mechanics (`02_ai_chess_coach.md`)
* **Verified Elements**: Explains chess concepts, points out move errors during practice and review, and suggests strategic improvements.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Underlying chess engine evaluation depth and latency targets.
  - Automated adaptive learning model specifics (whether the engine automatically scales difficulty dynamically in real-time).
  - Concrete taxonomy of mistake classifications (e.g., tactical blunders, positional inaccuracies, opening deviations).
  - Specific coaching feedback frequency during live gameplay vs. post-game review.

### Topic 03: Student Dashboard & Learning Activities (`03_student_features.md`)
* **Verified Elements**: Students sign in through the Student Dashboard.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Full catalog of interactive modules available post-login (e.g., daily puzzles, video lessons, bot matches).
  - Student rating calculation algorithm (e.g., Glicko-2, Elo, or internal learning score).
  - Direct student-to-coach messaging or homework submission mechanisms.
  - Gamification details (badges, streaks, leaderboards, achievement certificates).

### Topic 04: Parent Dashboard & Child Monitoring (`04_parent_features.md`)
* **Verified Elements**: Dedicated Parent Dashboard exists for monitoring child chess progress.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Specific visual reports available (e.g., weekly time spent, blunder trends, win/loss ratios).
  - Parental notification controls (email summaries, WhatsApp alerts, SMS notifications).
  - Multi-child profile switching under a single parent account.
  - Screen time limits and practice schedule controls.

### Topic 05: Coach Dashboard & Batch Management (`05_coach_features.md`)
* **Verified Elements**: Coaches manage batches and monitor student groups via Coach Dashboard.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Maximum batch size limits per coach tier.
  - Assignment creation tools (custom puzzle sets, opening repertoires).
  - Attendance tracking and automated homework grading.
  - Direct parent progress report generation and export capabilities.

### Topic 06: Academy & Organization Features (`06_academy_features.md`)
* **Verified Elements**: Zhatura Chess Academy serves academies and organizations; coaches manage batches.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Multi-tier role permissions (Super Admin, Branch Manager, Head Coach, Assistant Coach).
  - White-labeling or academy custom branding options.
  - Student and coach seat provisioning limits.
  - Institutional analytics dashboards for multi-branch performance tracking.

### Topic 07: Lessons & Practice Sessions (`07_lessons_sessions.md`)
* **Verified Elements**: Lessons and sessions constitute core learning activities. Missing lessons are account-specific.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Curriculum progression trees (Beginner, Intermediate, Advanced syllabus).
  - Live session scheduling workflows with human coaches vs. AI self-paced sessions.
  - Policy for rescheduling missed live sessions.
  - Prerequisites and unlock criteria for advanced lessons.

### Topic 08: Game Analysis Engine (`08_game_analysis.md`)
* **Verified Elements**: Analyzes chess moves, highlights mistakes, and recommends ideas.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - External PGN import/export support (e.g., importing games played on external platforms).
  - Annotation export format (downloadable PGN with AI text commentary).
  - Analysis depth limits based on user subscription level.

### Topic 09: Progress Tracking & Metrics (`09_progress_tracking.md`)
* **Verified Elements**: Progress tracking is accessible via Student and Parent dashboards.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Specific performance metrics tracked (tactical rating, opening accuracy %, endgame conversion rate).
  - Exportable PDF progress report cards for schools/academies.
  - Benchmark comparisons against peer cohorts of similar age or rating.

### Topic 10: Puzzles & Tactical Training (`10_puzzles_training.md`)
* **Verified Elements**: Platform includes tactical practice puzzles.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Total size and composition of puzzle database.
  - Puzzle categorization (e.g., pins, forks, skewers, back-rank mates, endgame drills).
  - Adaptive puzzle rating mechanics (gain/loss of rating points per puzzle).
  - Availability of interactive move hints and solution explanations.

### Topic 11: Plans, Packages & Pricing (`11_plans_pricing.md`) — **CRITICAL GAP**
* **Verified Elements**: **Currently NO verified pricing or plan details exist in public records.**
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Official plan names (e.g., Monthly Individual, Annual Student, Academy Multi-Seat).
  - Exact price points in INR (₹) and international currencies ($ USD).
  - Free trial duration (e.g., 7 days, 14 days, or limited freemium tier).
  - Refund policy window (e.g., 14-day money-back guarantee, non-refundable live sessions).
  - Renewal terms, cancellation procedures, and payment gateway options (UPI, Netbanking, Credit Cards).

### Topic 12: Account & Login Help (`12_account_login_help.md`)
* **Verified Elements**: Separate entry points for Student, Parent, and Coach dashboards.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Password recovery mechanics (SMS OTP vs. email verification link).
  - Single Sign-On (SSO) support (Google Sign-In, Apple ID).
  - Account deletion and data portability procedures.
  - Policy for child accounts without independent email addresses.

### Topic 13: Technical Support & Troubleshooting (`13_technical_support.md`)
* **Verified Elements**: General troubleshooting includes browser refresh, network verification, and device checks.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Standard Operating Procedures (SOP) for WebGL/browser canvas rendering failures.
  - WebSocket reconnection timeout behavior for live board synchronization.
  - Official cache-clearing recommendations for desktop and mobile clients.

### Topic 14: Multilingual Support (`14_multilingual_support.md`)
* **Verified Elements**: Voice support available in 11 Indian languages (English, Hindi, Bengali, Tamil, Telugu, Kannada, Malayalam, Marathi, Gujarati, Punjabi, Odia).
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Platform UI language localization availability (whether the web app UI is translated into all 11 languages).
  - Availability of multilingual chess notation (e.g., piece letters in regional languages).

### Topic 15: Frequently Asked Questions (`15_faq.md`)
* **Verified Elements**: 14 standard Q&As covering platform overview, coach role, dashboards, and security.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Answers for tournament preparation support.
  - FIDE rating equivalence estimates for Zhatura training levels.
  - Hardware board integration (e.g., Bluetooth electronic chessboards).

### Topic 16: Escalation & Human Support (`16_escalation_support.md`)
* **Verified Elements**: Callers can request human escalation; AI notes inquiries for support follow-up.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Stated Service Level Agreement (SLA) response times for callback (e.g., within 2 business hours, 24 hours).
  - Official customer support operating hours and weekly working days.
  - Direct support email address (e.g., `support@zhatura.com`).

### Topic 17: Organization & Custom Plans (`17_organization_custom_plans.md`)
* **Verified Elements**: Academy and school custom plans exist via direct inquiry.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Minimum seat threshold for institutional pricing (e.g., 25+ students, 100+ students).
  - Invoicing terms, GST compliance documentation, and annual contract discounts.
  - Onboarding and teacher training workshop provisions.

### Topic 18: Privacy, Child Safety & Security (`18_privacy_security.md`)
* **Verified Elements**: Support staff never ask for passwords or OTPs. No sensitive financial data collected on calls.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Compliance with the Digital Personal Data Protection Act (DPDP Act 2023, India).
  - Child online privacy safeguards (parental consent verification workflows).
  - Data storage residency confirmation (servers located within India).

### Topic 19: Supported Hardware & Platforms (`19_supported_platforms.md`)
* **Verified Elements**: Platform is accessible across modern browsers and devices.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Official Android app availability on Google Play Store.
  - Official iOS app availability on Apple App Store.
  - Minimum supported OS versions (e.g., iOS 15+, Android 10+, Chrome 110+).

### Topic 20: Common Customer Issues (`20_common_customer_issues.md`)
* **Verified Elements**: Structured responses for missing sessions, login trouble, and pricing requests.
* **Content Gaps (`CONTENT_REQUIRED`)**:
  - Clear workflow for accidental double payments.
  - Student transfer between coaches or academy branches.
  - Account reactivation after temporary hiatus.

---

## 3. Operational Safe Handling Protocols

When interacting with callers on `095-138-86363` or visitors on `/support`:
1. **Never Quote Invented Figures**: Under no circumstances should an agent or automated reply state a specific rupee or dollar figure.
2. **Standard Pricing Disclaimer**: *"Verified plan details and pricing are updated periodically. Please speak directly with our Customer Support team at 095-138-86363 to receive today's active plan options."*
3. **Account Access Safeguard**: Clearly notify users that AI automated agents do not possess direct read/write access to user database passwords or financial records.
4. **Structured Escalation**: Collect caller name, phone number, role, and inquiry summary to generate a support ticket for callback.
