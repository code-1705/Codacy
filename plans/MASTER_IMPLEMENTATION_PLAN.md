# FinGuard: Master Implementation Plan
## Production-Grade FinTech Verifiable Code Review Engine
### Track 1 — "The 24/7 Intelligent Code Reviewer" | AIM Code Kitchen S01

**Author:** 10-Year Principal FinTech Project Manager & Lead Systems Architect  
**Status:** Under Architectural Review (Pre-Implementation Gate)  
**Strict Directive:** No application code written until this plan and all subplans are audited and approved.

---

## 1. Executive Vision & Architectural Tenets

### 1.1 The Objective
Build, verify, publish, and benchmark a **locally-installed Python CLI package** (`pip install finguard`) that:
1. Reduces code review cycle time from **48 hours to <30 seconds** running entirely on the developer's machine.
2. Prevents double-spend, race conditions, floating-point currency errors, and unhandled idempotency keys with **verifiable repro tests**.
3. **Never sends raw source code off-device.** Only DLP-sanitized diffs reach the developer's own Vertex AI endpoint.
4. Conserves the **300 GCP credit points sandbox** budget by eliminating redundant LLM calls through local AST pre-screening.
5. Maintains an immutable **SOC2 / PCI-DSS compliant ACID audit trail** in local SQLite (or team-owned Cloud SQL).
6. Continuously learns from post-deploy CI flakiness and developer feedback via Bayesian rule reweighting.

### 1.2 Master System Flow

> [!IMPORTANT FIX — NEW-04]
> The Web Console (SUB-07) is **NOT** a sequential final step. It is a **persistent SSE consumer sidecar** that receives events in real time starting from Step 4 (Gemini stream). It runs in parallel, not after telemetry.

```
[ Developer ] ──POST /api/v1/review/start──▶ [ FastAPI Gateway ]
                                                      │
                ┌─────────────────────────────────────┤
                │  Synchronous Pre-Flight (<200ms)     │
                │                                     │
         ┌──────▼──────┐                   ┌──────────▼─────────┐
[ SUB-01: AST Engine ]             [ SUB-02: DLP & Quarantine ]
  $0.00 / 0ms filter                 Redact PAN, keys, secrets
  Idempotency & Float check          SHA-256 integrity hash
         └──────┬──────┘                   └──────────┬─────────┘
                └─────────────┬─────────────────────────┘
                              │
                              ▼
                 [ SUB-03: Cloud SQL + pgvector ]
                   ACID session log write
                   HNSW vector search → top-3 precedents
                   DB connection released within <30ms
                              │
                              │  ← Returns session_id to client
                              │
[ Developer ] ──GET /api/v1/review/stream/{session_id}──▶ SSE open
                              │
              ┌───────────────┴────────────────────────────────┐
              │  Parallel SSE Consumer (real-time)             │
              ▼                                                ▼
[ SUB-04: Vertex AI Gemini 1.5 Flash ]          [ SUB-07: Web Console ]
  Streams: init → ast_summary → chunk           SIDECAR — receives every
           → finding → repro_spec → complete    SSE event as it arrives.
              │                                 Renders live token stream,
              ▼                                 diff view, repro terminal.
[ SUB-05: Sandboxed Repro & Fix Engine ]
  Runs red→green test lifecycle
  Outputs verified patch diff
              │
              ▼ (async, after stream closes)
[ SUB-06: Telemetry & Bayesian Weight Loop ]
  Correlates CI reverts & dev feedback
  Updates rule weights in Cloud SQL
  Writes to learning_ledger.json
```

---

## 2. Slave Sub-Implementation Plan Matrix

The master architecture is divided into 7 modular, independently testable slave plans:

| Subplan ID | Focus Area | Responsible Sub-Agent | Document Reference |
| :--- | :--- | :--- | :--- |
| **SUB-01** | Token-Free AST Engine & Static Linters | `AGENT-AST-PERF` | [`plans/subplans/01_ast_engine_plan.md`](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/subplans/01_ast_engine_plan.md) |
| **SUB-02** | Local DLP Regex (primary) + Cloud DLP (optional enterprise) | `AGENT-SEC-DLP` | [`plans/subplans/02_security_dlp_plan.md`](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/subplans/02_security_dlp_plan.md) |
| **SUB-03** | Local SQLite (default) + Cloud SQL pgvector (optional enterprise) | `AGENT-SQL-VEC` | [`plans/subplans/03_cloudsql_pgvector_plan.md`](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/subplans/03_cloudsql_pgvector_plan.md) |
| **SUB-04** | Vertex AI Gemini 1.5 Flash SSE — called from dev's machine with dev's credentials | `AGENT-AI-STREAM` | [`plans/subplans/04_gemini_sse_stream_plan.md`](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/subplans/04_gemini_sse_stream_plan.md) |
| **SUB-05** | Sandboxed Repro QA & Patch Generator | `AGENT-REPRO-QA` | [`plans/subplans/05_sandboxed_repro_qa_plan.md`](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/subplans/05_sandboxed_repro_qa_plan.md) |
| **SUB-06** | Telemetry Ingestion & Dynamic Weighting | `AGENT-RETRO-LEARN` | [`plans/subplans/06_telemetry_retro_plan.md`](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/subplans/06_telemetry_retro_plan.md) |
| **SUB-07** | Parallel SSE Consumer — Web Console at `localhost:7432` | `AGENT-ORCHESTRATOR` | [`plans/subplans/07_web_console_dashboard_plan.md`](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/subplans/07_web_console_dashboard_plan.md) |
| **SUB-08** | **CLI Packaging & Local Distribution** (`pip install finguard`) | `AGENT-ORCHESTRATOR` | [`plans/subplans/08_cli_packaging_plan.md`](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/subplans/08_cli_packaging_plan.md) |

---

## 3. Phased Implementation Roadmap

### Phase 1: Core Engine & Ingestion (Days 1–3)
- Scaffold production FastAPI microservice structure.
- Implement SUB-01 (AST parser) and SUB-02 (DLP & injection quarantine).
- Establish Cloud SQL PostgreSQL schema with `pgvector` HNSW indexes (SUB-03).
- Implement local mock/fallback drivers so full test suites pass offline and in cloud.

### Phase 2: Vertex AI Streaming & Repro Sandbox (Days 4–6)
- Build Gemini 1.5 Flash SSE streaming endpoint with Pydantic JSON validation (SUB-04).
- Implement sandbox execution runner using isolated ephemeral processes / containers (SUB-05).
- Build automated test-patch-verify cycle (Fail-on-bug $\to$ Apply patch $\to$ Pass-on-fix).

### Phase 3: Telemetry Closed-Loop & Dashboard (Days 7–9)
- Implement feedback endpoints for CI flakiness and revert tracking (SUB-06).
- Implement Bayesian weight tuning algorithm updating Cloud SQL `review_rules`.
- Build the developer web console dashboard with real-time SSE token stream, visual diff viewer, and one-click patch downloader (SUB-07).

### Phase 4: Pilot Benchmark, Hardening & Screentest (Days 10–12)
- Execute synthetic FinTech benchmark suite (10 complex PRs containing realistic concurrency bugs, missing idempotency keys, and floating-point errors).
- Benchmark latency, token savings, and accuracy metrics.
- Record the direct-to-camera 3-minute screentest and prepare deployment documentation.

---

## 4. Quality Gates & Acceptance Criteria
* **Zero Secret Leakage:** 100% of test credentials and PANs masked by DLP before reaching LLM.
* **Token Efficiency:** $\ge 60\%$ of trivial/syntax/lint issues intercepted at Tier 0 without consuming Vertex AI tokens.
* **ACID Audit Integrity:** Every review session cryptographically hashed and committed to Cloud SQL.
* **Repro Verifiability:** 100% of synthesized repro tests demonstrate negative baseline (red) and post-patch resolution (green).
