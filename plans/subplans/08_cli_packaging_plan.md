# Subplan 08: CLI Packaging & Local Distribution (The Zero-Trust Entry Point)
**Owner:** `AGENT-ORCHESTRATOR`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope

Distribute FinGuard as a **locally-installed Python CLI package** — like Semgrep, ESLint, or Bandit. Developers install it once via `pip`, run it on their own machine, and their source code **never leaves their network**. They supply their own GCP credentials; FinGuard calls their Vertex AI endpoint on their behalf with their billing account.

> **Core Privacy Guarantee:** FinGuard never operates a shared cloud endpoint. Every team runs their own isolated instance. Code stays on-premises.

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
finguard review                      # Reviews current `git diff HEAD`
finguard review --staged             # Reviews `git diff --staged` (pre-commit)
finguard review --file payment.py    # Reviews a single file
finguard review --diff patch.diff    # Reviews an existing diff file
finguard review --severity critical  # Only surface CRITICAL findings

# Output modes
finguard review                      # Default: rich terminal output
finguard review --json               # Output raw FinGuardFinding JSON (for CI)
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

## 3. Local Server Architecture

`finguard review` and `finguard dashboard` both lazily spin up a local FastAPI process:

```
finguard review
       │
       ├─ Check if localhost:7432 is running
       │    ├─ Yes → POST diff directly to existing server
       │    └─ No  → Spawn uvicorn as a background subprocess on port 7432
       │              then POST diff to it
       │
       ├─ Wait for SSE stream on GET /api/v1/review/stream/{session_id}
       └─ Render findings in terminal (Rich) or open browser (--ui flag)
```

* Server process is **ephemeral by default**: exits when `finguard` CLI exits.
* Use `finguard dashboard` to keep the server alive persistently for team use.

---

## 4. Configuration System

### 4.1 Config File: `.finguard/config.yaml`
Committed to the repo root (secrets excluded via `.gitignore`):
```yaml
version: "1.0"
project_id: "my-gcp-project"          # GCP project with Vertex AI enabled
vertex_region: "us-central1"
model: "gemini-1.5-flash-001"

# Database (choose one):
database:
  backend: "sqlite"                    # Default: local SQLite
  sqlite_path: ".finguard/memory.db"
  # OR:
  # backend: "cloudsql"
  # dsn: "postgresql+asyncpg://user:pass@host/finguard_db"

# DLP (choose one):
dlp:
  backend: "local"                     # Default: local regex scrubber
  # OR:
  # backend: "cloud_dlp"              # Optional: full Google Cloud DLP API

# CI webhook HMAC secret (optional)
webhook_secret: ""                     # Populated by `finguard init`

# Behaviour
min_severity: "HIGH"                   # Only block commits at this level+
port: 7432
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

## 7. Privacy Guarantee Summary
| Data | Goes where | Who owns it |
| :--- | :--- | :--- |
| Raw source code | **Stays local** — never transmitted | Developer's machine |
| DLP-scrubbed diff | Sent to **their own** Vertex AI endpoint | Their GCP project |
| Findings & audit logs | Stored in **their** local SQLite or **their** Cloud SQL | Their infra |
| Learning ledger | `.finguard/` folder in **their** repo | Their team |
| FinGuard servers | **None — FinGuard has no backend** | N/A |
