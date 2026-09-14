# FinGuard — Intelligent FinTech Verifiable Code Review Engine
> **Track 1: "The 24/7 Intelligent Code Reviewer"**  
> **AIM Code Kitchen Season 01 (Presented by Google Cloud)**  
> *Joint Credit Line: created at Code Kitchen Season 01*

[![Google Cloud Run](https://img.shields.io/badge/GCP-Cloud%20Run-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/run)
[![Vertex AI Gemini 1.5 Flash](https://img.shields.io/badge/Vertex%20AI-Gemini%201.5%20Flash-34A853?logo=google&logoColor=white)](https://cloud.google.com/vertex-ai)
[![pgvector](https://img.shields.io/badge/Cloud%20SQL-pgvector-336791?logo=postgresql&logoColor=white)](https://cloud.google.com/sql)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg?logo=python&logoColor=white)](https://python.org)
[![Tests Passing](https://img.shields.io/badge/Pytest-96%20Passed%20(100%25)-brightgreen.svg)](tests/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

---

## 1. Executive Summary & Problem Landscape

In modern transactional financial systems (ledger processing, payment gateways, double-entry accounting, real-time gross settlement, and forex pipelines), a single escaped defect causes irreversible ledger corruption, catastrophic capital loss, and regulatory enforcement penalties.

### 1.1 The High-Stakes FinTech Dilemma
* **The 48-Hour Senior Review Bottleneck:** Pull requests carrying critical financial mutations linger for days waiting for senior distributed systems architects to manually trace race conditions and transaction boundaries.
* **Superficial & Subjective Reviews:** Human reviewers routinely miss non-obvious isolation failures, concurrent double-spend race conditions, unhandled saga rollbacks, and missing idempotency keys under high transaction load.
* **The High Cost and Danger of Blind LLMs:** Sending complete codebases directly to generic cloud LLMs burns massive token budgets on trivial linter/formatting errors while leaking unredacted cardholder data (PCI-DSS violations), API keys, and sensitive KYC credentials over the wire. Furthermore, untrusted code diffs expose review engines to adversarial prompt injection attacks designed to hijack AI reviewers into issuing unauthorized approval verdicts.

### 1.2 The FinGuard Breakthrough: Deterministic Defense + Generative Intelligence
**FinGuard** combines zero-cost, wire-speed deterministic static analysis with adversarial security guardrails and Google Vertex AI reasoning:
1. **Tier 0 Token-Free AST Filtering (<15ms, $0.00):** Executes local abstract syntax tree parsing to catch syntax errors, IEEE 754 float precision loss in currency operations, network calls held inside active database locks, and unprotected payment mutation routes before making any external API calls.
2. **Tier 1 Cloud DLP & Adversarial Firewall:** Automatically sanitizes cardholder data (using ISO/IEC 7812 Luhn checksums), Indian PAN cards, and production API secrets, while quarantining adversarial jailbreak attempts fail-closed.
3. **Tier 2 Semantic Memory Retrieval (Cloud SQL + pgvector):** Enriches incoming PR diffs with historical incident embeddings, post-mortem post-deploys, and organization-specific financial conventions.
4. **Tier 3 Vertex AI Gemini 1.5 Flash SSE Streaming:** Streams real-time, granular architectural analysis, root-cause explanations, and deterministic severity scores over Server-Sent Events.
5. **Tier 4 Sandboxed Repro & One-Click Patch:** Generates executable Pytest test cases that mathematically reproduce the flaw before applying a one-click unified diff patch.
6. **Tier 5 Closed-Loop Telemetry & Retrospective Learning:** Ingests CI flakiness and production telemetry to continuously calibrate AST rule weights and institutional memory in `.finguard/learning_ledger.json`.

**Outcome:** Slashes code review cycle latency from 48 hours to under 10 seconds while eliminating payment regressions and maintaining SOC2 / PCI-DSS compliance.

---

## 2. Global Multi-Tier Architecture

```
[ Developer Workstation (`finguard review`) / Git Hook / Web PR Console ]
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
     [ Tier 0: Local AST Gatekeeper ]   [ Tier 1: Local Secret / DLP Scrubber ]
      (Token-free static filter <15ms)   (Scrub keys, secrets, PANs on client)
               │                               │
               └───────────────┬───────────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼ (Default: `--cloud`)          ▼ (`--local` offline mode)
 ┌───────────────────────────────────────┐ ┌───────────────────────────────────────┐
 │ Cloud Run Ingestion Gateway (Hosted)  │ │ Localhost Ephemeral Engine (Port 7432)│
 │ - Workload Identity (Zero dev creds)  │ │ - Developer Local ADC                 │
 │ - Cloud DLP Enterprise Deep-Scan      │ │ - Local SQLite Database               │
 └──────────────────┬────────────────────┘ └──────────────────┬────────────────────┘
                    │                                         │
                    └────────────────────┬────────────────────┘
                                         ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │   Tier 2: Cloud SQL PostgreSQL + pgvector Engine (or Local SQLite)     │
 │  - Historical PR embeddings & ACID Audit Session Logs                  │
 │  - Weighted Rule Index (dynamically tuned by CI stats)                 │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │    Tier 3: Vertex AI Gemini 1.5 Flash Reasoning (SSE Stream)           │
 │   (Streams tokens in real time to CLI terminal & Web Console sidecar)  │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │    Tier 4: Automated Repro & One-Click Fix Engine                      │
 │  - Cloud Run Jobs / Local Docker Sandboxed Pytest Repro Synthesis      │
 │  - Unified Git Diff Patch for Zero-Context-Switching                   │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │  Tier 5: Closed-Loop Telemetry & Retrospective Learning                │
 │  - Correlates CI flakiness, reverts, & production bugs                 │
 │  - Dynamically updates vector weights & learning_ledger.json           │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core FinTech Capabilities

| Capability | Detection Method | Latency | Token Cost | FinTech Impact |
| :--- | :--- | :--- | :--- | :--- |
| **IEEE 754 Floating-Point Drift** | Tier 0 AST Parser (`AST-FIN-001`) | <2ms | $0.00 | Prevents fractional currency rounding errors. Enforces `Decimal`. |
| **Network Call in DB Lock** | Tier 0 AST Visitor (`AST-FIN-002`) | <3ms | $0.00 | Prevents connection pool starvation during slow Stripe/SWIFT calls. |
| **Missing Idempotency Key** | Tier 0 AST Decorator (`AST-IDEM-001`)| <2ms | $0.00 | Blocks duplicate charges and replay attacks on `/api/pay` routes. |
| **PCI-DSS & KYC PII Leaks** | Tier 1 DLP + Luhn Modulo-10 | <5ms | $0.00 | Zero credit card PANs, Indian PAN cards, or live keys committed. |
| **Adversarial Prompt Injection** | Tier 1 Adversarial Jailbreak Guard | <3ms | $0.00 | Quarantines attacker comments (`Dan mode`, `system override`). |
| **Double-Spend Balance Race** | Tier 3 Gemini 1.5 Flash + pgvector | ~8.5s | Minimal | Synthesizes `SELECT FOR UPDATE` pessimistic concurrency locks. |
| **Distributed 2PC Orphan Debit**| Tier 3 Gemini 1.5 Flash + Outbox | ~9.0s | Minimal | Enforces transactional outbox pattern and saga compensation. |
| **Multi-Language Node/Express** | Cross-Language AST & Heuristics | <10ms | $0.00 | Detects raw SQL concatenation and unawaited promises. |

---

## 4. Code Quality Metric (1 to 10 Formula)

FinGuard calculates an objective, deterministic 1–10 Code Quality Score:

$$\text{Score} = 10.0 - \min(9.0, \; 2.5 \cdot C + 1.0 \cdot H + 0.4 \cdot M + 0.1 \cdot L)$$

* **Grade A+ / A (9.0 – 10.0):** Production ready. Zero critical/high regressions.
* **Grade B (7.0 – 8.9):** Good standard. Minor optimizations or low-severity warnings.
* **Grade C (5.0 – 6.9):** Action required. Significant transactional or isolation concerns.
* **Grade F (< 5.0):** Blocked from merging. Critical payment/ledger risk detected.

---

## 5. Quickstart & Local Evaluation

### Prerequisites
* Python 3.11 or 3.12
* Git
* Google Cloud CLI (`gcloud`) or Google Gemini API Key (optional for local mode)

### 1. Installation
```bash
git clone https://github.com/your-org/finguard.git
cd finguard

python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run Diagnostics (Doctor Command)
```bash
python -m app.cli.main doctor
```
Output:
```text
🔬 Running FinGuard System Diagnostics...
  [PASS] Python Version: 3.12.7 (>= 3.11 required)
  [PASS] Git Workstation: repo='codeKitchenHack'
  [PASS] Tier 0 AST Engine: Functional (<15ms parser)
  [PASS] Tier 1 DLP Scrubber: Functional (Local Regex & Injection Guard)
  [PASS] Tier 2 Vector Memory Backend: local_sqlite
✅ FinGuard Diagnostics Complete.
```

### 3. Launch the FinGuard Web Console
```bash
python -m uvicorn app.server:app --host 127.0.0.1 --port 7432 --reload
```
Open **http://127.0.0.1:7432/** in your browser:
* Explore 7 realistic enterprise FinTech PR scenarios (Concurrency double-spend, IEEE float drift, Stripe pool leak, Distributed 2PC, PCI-DSS leak, Prompt injection, Node.js SQL injection).
* Stream Vertex AI reasoning tokens in real-time.
* View syntax-highlighted git diffs and 1-click patch applications.
* Inspect standalone shareable audit reports at `/report/<session-id>`.

### 4. Run CLI Review on Working Tree or PR
```bash
# Review current unstaged changes
python -m app.cli.main review

# Review a specific file
python -m app.cli.main review --file app/server.py

# Review staged changes and block commit if critical bugs found
python -m app.cli.main review --staged --severity critical

# Output JSON for CI/CD pipelines
python -m app.cli.main review --json
```

### 5. Run the Full Test Suite
```bash
pytest tests/ -v
# 96 passed in ~10s (100% green)
```

---

## 6. Official Google Cloud Run Deployment Guide

In accordance with AIM Code Kitchen Season 01 requirements, FinGuard is built strictly for **Google Cloud Platform** and packages directly onto **Cloud Run**.

### Step 1: GCP Project Setup
```bash
# Set your GCP Project ID
export PROJECT_ID="your-code-kitchen-project-id"
export REGION="us-central1"

gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

# Enable required GCP APIs
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    aiplatform.googleapis.com \
    dlp.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com
```

### Step 2: Build & Push Container Image
FinGuard includes an enterprise multi-stage [Dockerfile](Dockerfile) with SOC2 non-root execution:

```bash
# Submit build to Google Cloud Build
gcloud builds submit --tag gcr.io/$PROJECT_ID/finguard:latest .
```

### Step 3: Deploy to Google Cloud Run
```bash
gcloud run deploy finguard \
    --image gcr.io/$PROJECT_ID/finguard:latest \
    --platform managed \
    --region $REGION \
    --allow-unauthenticated \
    --port 8080 \
    --min-instances 1 \
    --max-instances 10 \
    --memory 2Gi \
    --cpu 2 \
    --set-env-vars "\
APP_ENV=production,\
GCP_PROJECT_ID=$PROJECT_ID,\
GCP_REGION=$REGION,\
VERTEX_LOCATION=$REGION,\
FINTECH_CREDIT=created at Code Kitchen Season 01"
```

### Step 4: Verify Production Service
```bash
# Retrieve production URL
export SERVICE_URL=$(gcloud run services describe finguard --format='value(status.url)')
echo "FinGuard Production Live at: $SERVICE_URL"

# Healthcheck
curl -s $SERVICE_URL/healthz
# Response: {"status":"healthy","service":"FinGuard Review Engine"}
```

---

## 7. Multi-Agent System Roster

All sub-agents communicate via immutable JSON finding contracts adhering to the `FinGuardFinding` specification:

* **`AGENT-ORCHESTRATOR`**: Principal FinTech PM & Systems Architect ([agents/orchestrator_pm.md](agents/orchestrator_pm.md)).
* **`AGENT-AST-PERF`**: Token-Free Static Analysis Engineer ([agents/ast_engine_agent.md](agents/ast_engine_agent.md)).
* **`AGENT-SEC-DLP`**: FinTech Security, DLP & Compliance Officer ([agents/security_dlp_agent.md](agents/security_dlp_agent.md)).
* **`AGENT-AI-STREAM`**: Vertex AI & Gemini 1.5 Flash Lead ([agents/gemini_stream_agent.md](agents/gemini_stream_agent.md)).
* **`AGENT-SQL-VEC`**: Cloud SQL & pgvector Data Architect ([agents/cloudsql_vector_agent.md](agents/cloudsql_vector_agent.md)).
* **`AGENT-REPRO-QA`**: Repro & Verification Test Engineer ([agents/repro_qa_agent.md](agents/repro_qa_agent.md)).
* **`AGENT-RETRO-LEARN`**: Telemetry, Revert & Continuous Learning Analyst ([agents/retro_learning_agent.md](agents/retro_learning_agent.md)).

---

## 8. Continuous Learning & Self-Correction Ledger

FinGuard adheres to a strict continuous learning protocol. Real-world feedback, CI flakiness, and human operator corrections are continuously ingested into [.finguard/learning_ledger.json](.finguard/learning_ledger.json) to dynamically calibrate AST and vector rule weights over time.

---

## 9. Deliverables & Joint Credit

* **Hackathon Track:** AIM Code Kitchen Season 01 — Track 1: The 24/7 Intelligent Code Reviewer
* **Joint Credit Line:** `created at Code Kitchen Season 01`
* **License:** Apache License 2.0
