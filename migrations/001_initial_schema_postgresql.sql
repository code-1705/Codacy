-- FinGuard Migration 001: Initial Schema (Google Cloud SQL PostgreSQL 16 + pgvector)
-- Created for Track 1: AIM Code Kitchen Season 01

-- 1. Enable Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 2. Table: Immutable Review Session Audit Logs (ACID)
CREATE TABLE IF NOT EXISTS review_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repo_name VARCHAR(255) NOT NULL,
    pr_id VARCHAR(64) NOT NULL,
    commit_sha VARCHAR(40) NOT NULL,
    author_id VARCHAR(128) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    findings_count INT DEFAULT 0,
    dlp_status VARCHAR(32) NOT NULL,
    execution_duration_ms INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. Table: Institutional Knowledge & Incident Vector Memory
CREATE TABLE IF NOT EXISTS historical_pr_incidents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pr_url VARCHAR(512) NOT NULL,
    bug_category VARCHAR(64) NOT NULL,
    description TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    remediation TEXT NOT NULL,
    fix_commit_sha VARCHAR(40) NOT NULL,
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 4. HNSW Vector Index for Sub-25ms Nearest Neighbor Cosine Search
CREATE INDEX IF NOT EXISTS idx_historical_pr_embeddings 
ON historical_pr_incidents 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 5. Table: Dynamic Rule Priority & CI Correlation
CREATE TABLE IF NOT EXISTS review_rules (
    rule_id VARCHAR(64) PRIMARY KEY,
    rule_name VARCHAR(255) NOT NULL,
    base_weight FLOAT DEFAULT 1.0,
    current_weight FLOAT DEFAULT 1.0,
    ci_flakiness_correlation FLOAT DEFAULT 0.0,
    revert_count INT DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
