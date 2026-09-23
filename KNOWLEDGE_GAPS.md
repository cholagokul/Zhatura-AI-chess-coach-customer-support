# Zhatura Knowledge Gaps

Generated: 2026-09-22
Method: sections explicitly marked `status: unavailable` or containing
"not yet documented in verified Zhatura sources" in the current
`prototype/knowledge/sources/` corpus.

These topics are intentionally **not answered** by the AI support agent
until approved Zhatura documentation is placed in the knowledge base.
The agent will say "I don't have verified information about that yet"
instead of inventing facts.

## Current Gaps

### Plans, Pricing and Subscriptions
- Exact plan names and tiers
- Price amounts in any currency
- Monthly vs yearly billing
- Student / parent / coach / academy plan differences
- Free-trial terms
- Discounts, refunds, renewal rules
- Payment methods and invoice details
- Organization / academy custom-plan pricing

### Lessons and Sessions
- How a lesson is structured
- How a session is scheduled or joined
- Lesson duration and content
- Progress storage details for lessons
- Specific troubleshooting steps when a session is unavailable

### Student Experience
- Full Student Dashboard feature list
- Exact learning activities after login
- Game history, achievements, ratings
- Coach-to-student interaction flow

### Parent Experience
- Detailed reports and session history visible to parents
- Parent controls and notifications
- Subscription access from the Parent Dashboard

### Coach Experience
- Per-student monitoring details
- Lesson and assignment creation
- Game review and feedback tools
- Coach communication channels
- AI assistance for coaches

### Academy / Organization
- Multi-student onboarding limits
- Coach/admin role permissions
- Organization dashboard reports
- Bulk-user pricing and contracts
- Academy scale limits and coach-student ratios

### Game Analysis
- Supported game sources (PGN upload, live games, etc.)
- Mistake categories and recommendation rules
- Review navigation and saving flow
- Connection to progress tracking and ratings

### Puzzles and Training
- Puzzle library size and themes
- Difficulty progression rules
- Scoring, hints and training mode behaviour
- Puzzle-to-lesson linkage

### Account and Login
- Password-reset process and URLs
- Account-creation flow
- Role switching
- Specific error messages and recovery steps

### Technical Support
- Verified troubleshooting steps for app/dashboard not loading
- Audio/voice issue resolution steps
- Browser/device compatibility matrix

### Privacy and Security
- Data-retention periods
- Encryption standards
- Compliance certifications
- Third-party subprocessors

### Supported Platforms
- Officially supported devices, OS versions, browsers and app stores
- Minimum system requirements

## How to Close a Gap

1. Obtain an **approved** Zhatura document (product spec, pricing sheet,
   support runbook, etc.).
2. Place or update the matching file under
   `prototype/knowledge/sources/`.
3. Set `verified: true` and a clear `provenance` line.
4. For pricing, set `source_type: approved_pricing` and keep
   `status: available` only when the data is final.
5. Run `cd prototype && python -m knowledge.build_index` to validate.
6. Restart the dev server (or live server when you are ready) to load the
   new corpus.
