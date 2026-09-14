# Subplan 03: Cloud SQL pgvector ACID & Memory Layer (Tier 2)
**Owner:** `AGENT-SQL-VEC`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope

Provide a dual-mode ACID audit and semantic memory layer for FinGuard. 
* **In Production Cloud Run (Hackathon Deployment):** Uses **Google Cloud SQL for PostgreSQL 16** with `pgvector` (`text-embedding-004`), providing scalable HNSW vector similarity search across historical incidents, satisfying GCP hackathon technical mandates and consuming allocated credits.
* **In Local / Offline CLI Mode:** Uses a local **SQLite** database (`.finguard/memory.db`) with in-process vector cosine distance calculation, ensuring developers can run disconnected without mandatory cloud infrastructure.

## 2. Technical Architecture

### 2.1 Dual-Backend Storage Model

**Tier A — Cloud SQL PostgreSQL 16 + pgvector (PRIMARY CLOUD RUN BACKEND)**
* Provisioned in Google Cloud for the hosted Cloud Run review service.
* Full `pgvector` HNSW index (`USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)`) for sub-25ms nearest-neighbor precedent retrieval.
* Multi-tenant ACID audit logs (`audit_sessions`) and persistent Bayesian rule weights (`review_rules`).
* Utilizes GCP Sandbox credits for managed database and Vertex embedding generation.

**Tier B — Local SQLite (OFFLINE / DEV ADAPTER)**
* Fallback when running `finguard review --local` or testing in CI without GCP credentials.
* File: `.finguard/memory.db` (git-ignored).
* Schema-compatible with PostgreSQL tables; uses Python-side / numpy cosine similarity for vector matching.

### 2.2 Shared Schema (Both Backends)
1. **`review_sessions`:** Append-only ACID log recording timestamp, commit SHA, PR identifier, author, DLP status, findings count, and SHA-256 integrity hash.
2. **`historical_pr_incidents`:** Institutional vector memory with past payment incident write-ups, root causes, fix diffs, and 768-dimensional embeddings via Vertex AI `text-embedding-004`.
3. **`review_rules`:** Dynamic rule registry storing rule weights ($W_i \in [0.2, 5.0]$), CI flakiness coefficients, and historical revert frequencies.

### 2.3 Vector Search Strategy by Backend
| Backend | Extension | Index | Latency |
| :--- | :--- | :--- | :--- |
| SQLite (local) | `sqlite-vec` | Flat cosine scan | <50ms (small corpus) |
| Cloud SQL (enterprise) | `pgvector` HNSW | `vector_cosine_ops` | <25ms (large corpus) |

Cosine similarity threshold `≥ 0.78` on both backends before forwarding precedent to Gemini.

### 2.4 Resilient Connection Pool
* SQLite: `aiosqlite` async driver, single-file connection, no pooling needed.
* Cloud SQL: `asyncpg` + SQLAlchemy async pool. Connections released within <30ms (SG-03).

## 3. Interface & Deliverables
* Module: `finguard/database/models.py`, `finguard/database/session.py`, `finguard/database/vector_store.py`, `finguard/database/backends/sqlite.py`, `finguard/database/backends/cloudsql.py`
* Migrations: `migrations/001_initial_schema.sql` (PostgreSQL), `migrations/001_initial_schema_sqlite.sql`
* Tests: `tests/test_database_vector.py` testing both backends — SQLite by default in CI, Cloud SQL in integration suite.
