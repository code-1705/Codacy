# Subplan 08: CLI Packaging & Local Distribution (The Zero-Trust Entry Point)
**Owner:** `AGENT-ORCHESTRATOR`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope

Distribute FinGuard as a **locally-installed Python CLI package** (`pip install finguard`) backed by an organization's private **Google Cloud Run review gateway** (satisfying Hackathon Deliverable #1). Developers run commands on their workstations (`git diff`), run deterministic AST checks locally with zero tokens, scrub PII and secrets via DLP, and stream findings either from their team's private Cloud Run service (using GCP Workload Identity) or locally via Application Default Credentials.

> **Core Privacy & Compliance Guarantee:** FinGuard operates zero public multi-tenant SaaS servers. Every organization deploys its own private Cloud Run gateway and Cloud SQL instance in its own Google Cloud project. Raw un-scrubbed repository source code stays on developer machines; only sanitized diffs are reviewed.

---

## 2. Distribution Model

### 2.1 Installation (PyPI)
```bash
# Standard install
pip install finguard

# Or zero-install run (like npx)
pipx run finguard review

# Or developer install from repo
pip install -e .
```

### 2.2 CLI Command Surface
```bash
# First-time setup wizard
finguard init
# → Prompts for: GCP Project ID, Vertex AI region, Cloud SQL DSN (optional),
#   local SQLite path (default), HMAC webhook secret (optional CI integration)
# → Writes config to .finguard/config.yaml in the repo

# Core review commands
finguard review                      # Reviews current `git diff HEAD` (via Cloud Run or local)
finguard review --cloud              # Explicitly routes via team Cloud Run service (default in team setup)
finguard review --local              # 100% offline mode (local AST + SQLite, no GCP network calls)
finguard review --staged             # Reviews `git diff --staged` (pre-commit)
finguard review --file payment.py    # Reviews a single file
finguard review --diff patch.diff    # Reviews an existing diff file
finguard review --severity critical  # Only surface CRITICAL findings

# Output modes
finguard review                      # Default: rich terminal output
finguard review --json               # Output raw FinGuardFinding JSON (for CI)
finguard review --ui                 # Launches interactive web console at localhost:7432
finguard review --no-ui              # Suppress web dashboard, print to stdout only

# Git hook management
finguard install-hook                # Installs as pre-commit git hook
finguard uninstall-hook             # Removes hook

# Web dashboard
finguard dashboard                   # Opens localhost:7432 in browser

# Telemetry (team usage)
finguard feedback accept <finding-id>   # Record accepted patch
finguard feedback reject <finding-id>   # Record false positive dismissal

# Version & diagnostics
finguard --version
finguard doctor                      # Health-checks GCP creds, SQLite/Cloud SQL, Vertex AI
```

### 2.3 Git Hook Integration
Running `finguard install-hook` injects the following into `.git/hooks/pre-commit`:
```bash
#!/bin/sh
finguard review --staged --severity critical
if [ $? -ne 0 ]; then
  echo "FinGuard: CRITICAL findings detected. Fix before committing."
  exit 1
fi
```
* Hook exits `1` and blocks commit only when **CRITICAL** findings are present.
* `HIGH` and lower are reported but do not block — developer sees them in the terminal and can proceed.

---

## 3. Review Routing & Server Architecture

FinGuard CLI intelligently routes reviews according to the configured execution mode:

```
finguard review
       │
       ├─ Mode Determination:
       │    ├─ Cloud Run Mode (Default when `cloud_run_url` configured or `--cloud` flag):
       │    │    ├─ 1. Run local AST Gatekeeper (Tier 0, 0ms, 0 tokens)
       │    │    ├─ 2. Run local DLP Scrubbing (Tier 1 pre-flight on diff)
       │    │    ├─ 3. POST sanitized diff to {cloud_run_url}/api/v1/review/start
       │    │    ├─ 4. Stream SSE from {cloud_run_url}/api/v1/review/stream/{session_id}
       │    │    └─ 5. Cloud Run uses Workload Identity (no workstation credentials)
       │    │
       │    └─ Local Mode (`mode: local` or `--local` flag):
       │         ├─ 1. Check if localhost:7432 is running (spawn uvicorn if not)
       │         ├─ 2. POST diff to http://localhost:7432/api/v1/review/start
       │         ├─ 3. Stream SSE from http://localhost:7432/api/v1/review/stream/{session_id}
       │         └─ 4. Uses local SQLite memory + developer's gcloud ADC
       │
       └─ Output: Render Rich CLI terminal UI or open browser (--ui flag)
```

* Cloud Run mode centralizes audit logs in team Cloud SQL and prevents credentials from residing on workstations.
* Local mode allows complete disconnected operation or offline debugging.
* In local mode, the uvicorn process is **ephemeral by default** (terminates when the CLI exits) unless started via `finguard dashboard`.

---

## 4. Configuration System

### 4.1 Config File: `.finguard/config.yaml`
Committed to the repo root (secrets excluded via `.gitignore`):
```yaml
version: "1.0"
mode: "cloud"                          # "cloud" (team Cloud Run gateway) or "local" (standalone offline)
cloud_run_url: "https://finguard-backend-xyz.a.run.app" # Production Cloud Run Service URL (Deliverable #1)

# GCP Project settings (used for Cloud Run deployment and local ADC fallback)
project_id: "my-gcp-project"          # GCP project with Vertex AI enabled
vertex_region: "us-central1"
model: "gemini-1.5-flash-001"

# Database (used by Cloud Run or local mode):
database:
  backend: "sqlite"                    # "sqlite" for local, "cloudsql" for Cloud Run
  sqlite_path: ".finguard/memory.db"
  # OR:
  # backend: "cloudsql"
  # dsn: "postgresql+asyncpg://user:pass@host/finguard_db"

# DLP (choose one):
dlp:
  backend: "local"                     # Default: fast local regex scrubber
  # OR:
  # backend: "cloud_dlp"              # Optional: full Google Cloud DLP API

# CI webhook HMAC secret (optional)
webhook_secret: ""                     # Populated by `finguard init`

# Behaviour
min_severity: "HIGH"                   # Only block commits at this level+
port: 7432                             # Local dashboard / ephemeral server port
```

### 4.2 Secrets (never committed)
Added to `.gitignore` automatically by `finguard init`:
```
.finguard/config.secrets.yaml        # GCP service account JSON path
.finguard/memory.db                  # Local SQLite institutional memory
```

### 4.3 GCP Credential Resolution (Standard ADC Chain)
```
1. GOOGLE_APPLICATION_CREDENTIALS env var (service account JSON)
2. gcloud auth application-default login (developer machine)
3. Workload Identity (inside GCP VMs/Cloud Run — if team chooses to run hosted)
```
No credential is stored inside FinGuard — standard Google Application Default Credentials.

---

## 5. PyPI Packaging Spec

### 5.1 `pyproject.toml` Entry Points
```toml
[project]
name = "finguard"
version = "1.0.0"
description = "Token-free FinTech code reviewer with Vertex AI streaming — created at Code Kitchen Season 01"
requires-python = ">=3.11"

[project.scripts]
finguard = "finguard.cli.main:app"

[project.dependencies]
typer = ">=0.12"
rich = ">=13.0"
uvicorn = ">=0.29"
fastapi = ">=0.111"
httpx = ">=0.27"
```

### 5.2 Package Structure
```
finguard/
├── cli/
│   ├── main.py          # Typer CLI entrypoint (finguard review, init, etc.)
│   ├── server.py        # Localhost server lifecycle manager
│   └── output.py        # Rich terminal renderer for findings
├── ast_engine/          # SUB-01
├── security/            # SUB-02
├── database/            # SUB-03
├── ai/                  # SUB-04
├── sandbox/             # SUB-05
├── telemetry/           # SUB-06
└── static/              # SUB-07 (web console assets)
```

---

## 6. Interface & Deliverables
* Module: `finguard/cli/main.py`, `finguard/cli/server.py`, `finguard/cli/output.py`
* Config: `.finguard/config.yaml` template generated by `finguard init`
* Hook: `finguard install-hook` script injector
* Tests: `tests/test_cli.py` asserting all CLI commands execute and return correct exit codes.

---

## 7. Privacy & Infrastructure Governance Summary
| Component / Data | Destination & Execution | Ownership & Security Boundary |
| :--- | :--- | :--- |
| **Raw Repository Source Code** | **Never leaves developer's workstation** | Developer machine / local filesystem |
| **AST Pre-Check (Tier 0)** | Local Python AST execution (0ms, 0 tokens) | Developer machine |
| **Sanitized Code Diff (Tier 1)** | Transmitted to private Cloud Run gateway over TLS | Organization's private GCP Project VPC |
| **AI Reasoning (Tier 3)** | Google Vertex AI (`gemini-1.5-flash-001`) via Workload Identity | Organization's GCP Project & Billing |
| **Audit Logs & Embeddings (Tier 2)** | Organization's Cloud SQL (`pgvector`) or local SQLite | Organization's private database |
| **Public Multi-Tenant SaaS** | **NONE** — FinGuard operates no external SaaS servers | Zero third-party data leakage |
| **Production Cloud Run Service** | Dedicated Cloud Run deployment (Deliverable #1) | Hosted inside organization's GCP project |
