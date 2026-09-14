"""
FinGuard Subplan 09 Test Suite
Validates:
1. Standardized 1-10 code quality rating formula.
2. Historical CSV learning ingestion (<id>, <type>, <description>).
3. Multi-language detection & guidance.
4. Persistent user session history & developer growth tracking.
"""
import pytest
from app.scoring import calculate_quality_rating, QualityRating
from app.multilang import detect_language, get_language_guidelines
from app.csv_ingestion import parse_historical_csv_content, ingest_csv_into_database
from app.database.sqlite_backend import SQLiteDatabaseBackend
from app.database.models import ReviewSession


# --- 1. Quality Rating (1 to 10 Scale) Tests ---

def test_quality_rating_clean_code():
    findings = []
    rating = calculate_quality_rating(findings)
    assert rating.score == 10.0
    assert rating.grade == "A+"
    assert rating.penalty_points == 0.0
    assert "Production Ready" in rating.verdict


def test_quality_rating_critical_penalty():
    # 1 critical defect (-2.5) -> 7.5 (Grade B)
    findings = [{"severity": "CRITICAL", "category": "RACE_CONDITION"}]
    rating = calculate_quality_rating(findings)
    assert rating.score == 7.5
    assert rating.grade == "B"
    assert rating.critical_defects == 1


def test_quality_rating_multiple_critical_clamps_at_one():
    # 5 critical defects (-12.5) -> Clamped at minimum 1.0 (Grade F)
    findings = [{"severity": "CRITICAL"} for _ in range(5)]
    rating = calculate_quality_rating(findings)
    assert rating.score == 1.0
    assert rating.grade == "F"
    assert "Deployment Blocked" in rating.verdict


def test_quality_rating_mixed_defects():
    findings = [
        {"severity": "HIGH"},     # -1.5
        {"severity": "MEDIUM"},   # -0.8
        {"severity": "LOW"}       # -0.3
    ]
    # Total penalty: 2.6 -> 10.0 - 2.6 = 7.4
    rating = calculate_quality_rating(findings)
    assert rating.score == 7.4
    assert rating.grade == "C"


# --- 2. Multi-Language Detection & Heuristics Tests ---

def test_language_detection_by_extension():
    assert detect_language("", "main.go") == "go"
    assert detect_language("", "App.tsx") == "typescript"
    assert detect_language("", "server.js") == "javascript"
    assert detect_language("", "Service.java") == "java"
    assert detect_language("", "audit.py") == "python"


def test_language_detection_by_syntax():
    go_code = "package main\nimport \"fmt\"\nfunc main() {}"
    assert detect_language(go_code) == "go"

    java_code = "public class PaymentGateway { public void charge() {} }"
    assert detect_language(java_code) == "java"

    ts_code = "interface PaymentPayload {\n  amount: number;\n}"
    assert detect_language(ts_code) == "typescript"

    js_code = "const express = require('express');\nconst app = express();"
    assert detect_language(js_code) == "javascript"


def test_language_guidelines_retrieval():
    guidelines = get_language_guidelines("go")
    assert guidelines.language == "go"
    assert any("decimal" in p.lower() or "int64" in p.lower() for p in guidelines.best_practices)
    assert any("goroutine" in a.lower() for a in guidelines.common_anti_patterns)


# --- 3. Historical CSV Ingestion Tests (<id>, <type>, <description>) ---

def test_parse_historical_csv():
    csv_sample = """id, type, description
1, formatting, Avoid single-character variable names — they hurt readability
2, performance, Cache repeated database lookups inside the request loop
3, security, Never interpolate raw user input directly into SQL queries
"""
    records = parse_historical_csv_content(csv_sample)
    assert len(records) == 3
    assert records[0].rule_id == "CSV-HIST-1"
    assert records[0].rule_type == "formatting"
    assert "single-character" in records[0].description
    assert len(records[0].embedding) == 768

    assert records[2].rule_type == "security"
    assert "SQL queries" in records[2].description


def test_ingest_csv_into_sqlite(tmp_path):
    db_file = str(tmp_path / "test_memory.db")
    backend = SQLiteDatabaseBackend(db_path=db_file)

    csv_data = """1, formatting, Avoid single-character variable names
2, concurrency, Always lock account row before debiting
"""
    result = ingest_csv_into_database(csv_data, backend)
    assert result["status"] == "SUCCESS"
    assert result["ingested_count"] == 2

    # Check rule was stored in SQLite review_rules
    rule = backend.get_rule("CSV-HIST-1")
    assert rule is not None
    assert "FormattingGuard" in rule.rule_name


# --- 4. Persistent User Session History & Developer Growth Tests ---

def test_user_growth_progression(tmp_path):
    db_file = str(tmp_path / "test_growth.db")
    backend = SQLiteDatabaseBackend(db_path=db_file)

    # Initially empty user
    growth_init = backend.get_user_growth("alice_dev")
    assert growth_init["total_reviews"] == 0
    assert growth_init["improvement_delta"] == 0.0

    # Record 3 review sessions over time with improving scores
    session1 = ReviewSession(
        id="sess-001",
        repo_name="org/wallet",
        pr_id="pr-101",
        commit_sha="sha1",
        author_id="alice@fintech.corp",
        payload_hash="hash1",
        findings_count=3,
        dlp_status="CLEAN",
        execution_duration_ms=120,
        quality_score=4.5,
        user_id="alice_dev",
        language="python"
    )
    session2 = ReviewSession(
        id="sess-002",
        repo_name="org/wallet",
        pr_id="pr-102",
        commit_sha="sha2",
        author_id="alice@fintech.corp",
        payload_hash="hash2",
        findings_count=1,
        dlp_status="CLEAN",
        execution_duration_ms=95,
        quality_score=7.8,
        user_id="alice_dev",
        language="python"
    )
    session3 = ReviewSession(
        id="sess-003",
        repo_name="org/wallet",
        pr_id="pr-103",
        commit_sha="sha3",
        author_id="alice@fintech.corp",
        payload_hash="hash3",
        findings_count=0,
        dlp_status="CLEAN",
        execution_duration_ms=80,
        quality_score=9.5,
        user_id="alice_dev",
        language="go"
    )

    backend.log_session(session1)
    backend.log_session(session2)
    backend.log_session(session3)

    # Query growth trajectory
    growth = backend.get_user_growth("alice_dev")
    assert growth["total_reviews"] == 3
    assert growth["initial_score"] == 4.5
    assert growth["latest_score"] == 9.5
    assert growth["improvement_delta"] == 5.0  # Grew by +5.0 points!
    assert growth["language_distribution"]["python"] == 2
    assert growth["language_distribution"]["go"] == 1
    assert len(growth["score_trajectory"]) == 3
