# Subplan 04: Vertex AI Gemini 1.5 Flash SSE Pipeline (Tier 3)
**Owner:** `AGENT-AI-STREAM`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope

Provide real-time, low-latency streaming code audits over Server-Sent Events (SSE) using Google Vertex AI (`gemini-1.5-flash-001`), streaming structured JSON chunks adhering to the `FinGuardFinding` contract.

> **Hybrid Execution & Credential Governance:**
> FinGuard operates with dual execution paths for Gemini 1.5 Flash:
> 1. **Cloud Run Gateway (Team Deployment / Deliverable #1):** The CLI forwards the DLP-sanitized diff to the organization's dedicated Cloud Run service. Cloud Run securely invokes Vertex AI using GCP **Workload Identity** (no long-lived service account keys stored on developer workstations).
> 2. **Local CLI Mode (Offline / Standalone Developer):** When running locally without Cloud Run, FinGuard invokes Vertex AI directly using the developer's local Application Default Credentials (`gcloud auth application-default login`).
> In both modes, **only the DLP-sanitized diff** (never un-sanitized source code or credentials) is transmitted to Vertex AI. Every team's Gemini calls hit their own GCP project and billing account.

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
