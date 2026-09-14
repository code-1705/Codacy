# FinGuard Subplan 09: Multi-Language Reviews, 1-10 Quality Rating, CSV Historical Learning & User Growth Tracking

## 1. Context & Competition Directive Alignment
Directly satisfies the official Code Kitchen Season 01 Track 1 prompt specifications:
1. **Multi-language Reviews:** Secure code submission with language-aware bug reports, architectural best-practice guidance, and optimization insights across **Python, JavaScript/TypeScript, Go, and Java**.
2. **Standardized Code Quality Rating (1 to 10 Scale):** Mathematical grading engine assigning a clear, standardized rating from 1.0 to 10.0 based on severity, defect frequency, and architectural cleanliness.
3. **Historical CSV Learning Ingestion:** Ingestion engine parsing CSV files matching `<id>, <type>, <description>` (e.g., `1, formatting, Avoid single-character variable names`, `2, performance, Cache repeated database lookups`, `3, security, Never interpolate raw user input`), converting them into vector memory to inform and enrich code reviews.
4. **Persistent User Session History & Growth Tracking:** User-centric history tracking score progression over time, showing developer mastery, recurring flaw trends, and improvement velocity.

---

## 2. Technical Architecture & Schemas

### 2.1 Standardized Quality Score (1 to 10 Scale)
Algorithm:
- Base score: $10.0$
- Deductions:
  - Critical severity defect: $-2.5$ each
  - High severity defect: $-1.5$ each
  - Medium severity defect: $-0.8$ each
  - Low severity defect: $-0.3$ each
  - Audit note: $-0.1$ each
- Normalized Range: $[1.0, 10.0]$
- Grade tiers:
  - $9.0 - 10.0$: Excellent (Production Ready)
  - $7.5 - 8.9$: Good (Minor Optimizations)
  - $5.0 - 7.4$: Needs Improvement (Transactional or Performance Warnings)
  - $1.0 - 4.9$: Critical (Deployment Blocked)

### 2.2 Historical CSV Ingestion Engine
- Input Schema: `<id>, <type>, <description>`
- Endpoint: `POST /api/v1/rules/ingest-csv` (accepts CSV text or file upload)
- CLI Command: `finguard ingest-csv <path.csv>`
- Storage & Vectorization: Embeds each historical rule description and stores in `review_rules` with category and source metadata.

### 2.3 Multi-Language Review Profiles
- Supported: `python`, `javascript`, `typescript`, `go`, `java`
- Auto-detection based on file extension, syntax patterns, or explicit user selection.
- Language-specific architectural best practices and anti-pattern checklists passed into Gemini prompt and localized heuristic rules.

### 2.4 User Growth & History Tracking
- User session link: `user_id` stored on each review session.
- Endpoint: `GET /api/v1/users/{user_id}/growth`
- Returns:
  - Total reviews conducted
  - Historical scores with timestamps
  - Average score progression (rolling average)
  - Defect frequency breakdown (Security, Performance, Ledger, Formatting)
  - Improvement trajectory (% score increase over time)
- Web Console: Interactive "Developer Growth" tab with visual progress charts.

---

## 3. Verification Plan
- Unit test CSV parser for `<id>, <type>, <description>`.
- Unit test quality score formula across 0-defect, minor-defect, and critical-defect scenarios.
- Unit test multi-language review flow (Python, JS, Go, Java).
- Unit test user growth history aggregator.
- Full regression test verifying all 86 existing tests still pass.
