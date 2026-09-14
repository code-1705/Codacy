# Subplan 03: Cloud SQL pgvector ACID & Memory Layer (Tier 2)
**Owner:** `AGENT-SQL-VEC`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope

Provide a local-first, zero-infrastructure memory and audit layer for FinGuard. By default everything is stored in a local **SQLite** database inside the developer's `.finguard/` folder. For enterprise teams, this layer can optionally be upgraded to **Google Cloud SQL for PostgreSQL 16** with `pgvector` for shared institutional memory across a team.

> **Architecture Shift:** There is no mandatory cloud database. A solo developer or a team trialling FinGuard should get full functionality — audit logs, vector search, rule weights — from a single local file.

## 2. Technical Architecture

### 2.1 Two-Backend Storage Model

**Tier A — Local SQLite (DEFAULT)**
* Zero cloud dependency. Works immediately after `finguard init`.
* File: `.finguard/memory.db` (added to `.gitignore` automatically).
* Uses `sqlite-vec` extension for approximate vector similarity search (cosine).
* Tables: `review_sessions`, `historical_pr_incidents`, `review_rules` (same schema, SQLite dialect).
* Suitable for individual developers and small teams.

**Tier B — Cloud SQL PostgreSQL 16 + pgvector (OPTIONAL ENTERPRISE)**
* Enabled via `.finguard/config.yaml`: `database.backend: cloudsql`.
* Shared institutional memory across the entire engineering team.
* Full `pgvector` HNSW index (`USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)`) for sub-25ms nearest-neighbor search.
* Tables: `review_sessions`, `historical_pr_incidents`, `review_rules`.
* Teams bring their own Cloud SQL instance — FinGuard never hosts a shared database.

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
