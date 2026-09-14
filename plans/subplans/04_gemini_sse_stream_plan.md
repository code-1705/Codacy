# Subplan 04: Vertex AI Gemini 1.5 Flash SSE Pipeline (Tier 3)
**Owner:** `AGENT-AI-STREAM`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope

Provide real-time, low-latency streaming code audits over Server-Sent Events (SSE) using Google Vertex AI (`gemini-1.5-flash-001`), streaming structured JSON chunks adhering to the `FinGuardFinding` contract.

> **Credential Ownership:** FinGuard makes Vertex AI API calls **from the developer's local machine** using **their own GCP credentials** (Application Default Credentials or service account). FinGuard has no shared backend, no proxy, and no API key of its own. Every team's Gemini calls hit their own project and their own billing account. Only the **DLP-sanitized diff** (never raw source) is transmitted.

## 2. Technical Architecture

### 2.1 Prompt Engineering & Grounding
* System Prompt primes the model on FinTech invariants:
  * Double-entry ledger balance constraints
  * Transaction isolation anomalies (Dirty reads, Non-repeatable reads, Phantom reads)
  * Distributed lock ordering & deadlock prevention
  * Out-of-order webhook reconciliation
* Context Grounding: Directly feeds the sanitized diff, deterministic AST output, and top-3 historical PR incident precedents from Cloud SQL `pgvector`.

### 2.2 Two-Step Review Handshake (POST → GET)

> [!IMPORTANT FIX — NEW-01]
> `GET` cannot carry a request body. The diff payload (potentially 50KB+) must be submitted separately before the SSE stream opens. The review lifecycle is two steps:

**Step 1 — Ingest (POST):**
```
POST /api/v1/review/start
Body: { diff: string, repo: string, commit_sha: string, author_id: string }
Response: { session_id: "uuid-v4", status: "QUEUED" }
```
* Receives raw diff, runs DLP + AST synchronously, creates ACID session row, fetches pgvector precedents.
* Returns `session_id` immediately (< 200ms). No SSE yet.

**Step 2 — Stream (GET):**
```
GET /api/v1/review/stream/{session_id}
Content-Type: text/event-stream
```
* Client opens SSE connection using the `session_id` returned from Step 1.
* Server streams Gemini analysis against the already-processed session context.
* Stream events:
  * `event: init` → Metadata, session ID, DLP status
  * `event: ast_summary` → Pre-flight zero-token findings
  * `event: chunk` → Real-time token streaming of reasoning
  * `event: finding` → Structured Pydantic `FinGuardFinding` object
  * `event: repro_spec` → Generated test and patch
  * `event: complete` → Final token usage, latency metrics, audit hash

### 2.3 Structured Output Validation
* Implements Gemini structured function calling / Pydantic schema enforcement to eliminate unparseable JSON errors.

## 3. Interface & Deliverables
* Module: `app/ai/gemini_service.py`, `app/ai/prompts.py`, `app/ai/sse_streamer.py`
* Tests: `tests/test_gemini_stream.py` with mock streaming generator and payload validator.
