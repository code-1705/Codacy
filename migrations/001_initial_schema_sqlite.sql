-- FinGuard Migration 001: Initial Schema (Local SQLite / Offline Mode)
-- Created for Track 1: AIM Code Kitchen Season 01

-- 1. Table: Review Sessions Audit Table (ACID)
CREATE TABLE IF NOT EXISTS review_sessions (
    id TEXT PRIMARY KEY,
    repo_name TEXT NOT NULL,
    pr_id TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    author_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    findings_count INTEGER DEFAULT 0,
    dlp_status TEXT NOT NULL,
    execution_duration_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

-- 2. Table: Historical PR Incidents Vector Table
CREATE TABLE IF NOT EXISTS historical_pr_incidents (
    id TEXT PRIMARY KEY,
    pr_url TEXT NOT NULL,
    bug_category TEXT NOT NULL,
    description TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    remediation TEXT NOT NULL,
    fix_commit_sha TEXT NOT NULL,
    embedding_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 3. Table: Dynamic Rule Priority & CI Correlation
CREATE TABLE IF NOT EXISTS review_rules (
    rule_id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL,
    base_weight REAL DEFAULT 1.0,
    current_weight REAL DEFAULT 1.0,
    ci_flakiness_correlation REAL DEFAULT 0.0,
    revert_count INTEGER DEFAULT 0,
    last_updated TEXT NOT NULL
);
