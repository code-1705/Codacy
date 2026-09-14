"""
Unit Tests for FinGuard Tier 2: Cloud SQL & pgvector Memory Layer
Validates ACID session logging, deterministic embeddings, in-process cosine similarity, and dynamic rule weighting.
"""
import pytest
import os
import uuid
from app.database.models import ReviewSession, HistoricalIncident, ReviewRule
from app.database.manager import DatabaseManager
from app.database.vector_math import (
    cosine_similarity,
    generate_deterministic_embedding,
    EMBEDDING_DIM
)


@pytest.fixture
def db_manager(tmp_path):
    db_file = str(tmp_path / "test_memory.db")
    return DatabaseManager(backend="sqlite", sqlite_path=db_file)


# --- 1. Vector Math & Embedding Invariants ---

def test_cosine_similarity_properties():
    # Identical vectors -> 1.0
    v1 = [0.5, 0.5, 0.5, 0.5]
    assert pytest.approx(cosine_similarity(v1, v1), 0.0001) == 1.0

    # Orthogonal vectors -> 0.0
    v_orth1 = [1.0, 0.0, 0.0]
    v_orth2 = [0.0, 1.0, 0.0]
    assert pytest.approx(cosine_similarity(v_orth1, v_orth2), 0.0001) == 0.0

    # Opposite vectors -> -1.0
    v_neg = [-0.5, -0.5, -0.5, -0.5]
    assert pytest.approx(cosine_similarity(v1, v_neg), 0.0001) == -1.0

    # Zero vectors -> 0.0
    v_zero = [0.0, 0.0, 0.0, 0.0]
    assert cosine_similarity(v1, v_zero) == 0.0


def test_deterministic_embedding_generation():
    text1 = "Concurrent withdrawal race condition on wallet balance"
    emb1 = generate_deterministic_embedding(text1)
    
    assert len(emb1) == EMBEDDING_DIM
    # Check unit vector property (sum of squares ~ 1.0)
    norm = sum(x * x for x in emb1)
    assert pytest.approx(norm, 0.01) == 1.0

    # Same text produces identical vector
    emb2 = generate_deterministic_embedding(text1)
    assert emb1 == emb2


# --- 2. ACID Review Session Audit Logging ---

def test_log_and_retrieve_review_session(db_manager):
    session_id = str(uuid.uuid4())
    session = ReviewSession(
        id=session_id,
        repo_name="org/payments-engine",
        pr_id="PR-992",
        commit_sha="e5f6a1b2c3d478901234567890abcdef12345699",
        author_id="dev-alice@fintech.corp",
        payload_hash="sha256:d60455376ead5d40aa16dee1231a04ecde820200865ae813e2a1627ceac9892f",
        findings_count=3,
        dlp_status="CLEAN",
        execution_duration_ms=184
    )

    logged_id = db_manager.log_session(session)
    assert logged_id == session_id

    retrieved = db_manager.get_session(session_id)
    assert retrieved is not None
    assert retrieved.id == session_id
    assert retrieved.repo_name == "org/payments-engine"
    assert retrieved.commit_sha == "e5f6a1b2c3d478901234567890abcdef12345699"
    assert retrieved.findings_count == 3
    assert retrieved.payload_hash.startswith("sha256:")
    assert retrieved.execution_duration_ms == 184


# --- 3. Semantic Vector Search for FinTech Incident Precedents ---

def test_matches_double_spend_precedent(db_manager):
    query = "Concurrent withdrawal debit race condition balance below zero SELECT FOR UPDATE"
    result = db_manager.search_precedents_by_text(query, top_k=2, min_similarity=0.75)

    assert len(result.matched_precedents) > 0
    top_precedent = result.matched_precedents[0]
    assert top_precedent.bug_category == "DOUBLE_SPEND_RACE"
    assert top_precedent.similarity_score >= 0.75
    assert "wallet" in top_precedent.description.lower() or "race" in top_precedent.description.lower()
    assert "FOR UPDATE" in top_precedent.remediation
    # Checks elevated rules
    assert "RULE-RACE-CONDITION" in result.elevated_rules
    assert "AST-FIN-004" in result.elevated_rules


def test_matches_missing_idempotency_precedent(db_manager):
    query = "Missing idempotency key payment route webhook retry charge twice"
    result = db_manager.search_precedents_by_text(query, top_k=2, min_similarity=0.75)

    assert len(result.matched_precedents) > 0
    top_precedent = result.matched_precedents[0]
    assert top_precedent.bug_category == "MISSING_IDEMPOTENCY_RETRY"
    assert "AST-FIN-002" in result.elevated_rules
    assert "RULE-RETRY-IDEMPOTENCY" in result.elevated_rules


def test_matches_float_precision_drift_precedent(db_manager):
    query = "Float calculation IEEE 754 precision drift ledger mismatch"
    result = db_manager.search_precedents_by_text(query, top_k=2, min_similarity=0.75)

    assert len(result.matched_precedents) > 0
    top_precedent = result.matched_precedents[0]
    assert top_precedent.bug_category == "FLOAT_PRECISION_DRIFT"
    assert "AST-FIN-001" in result.elevated_rules


def test_matches_transaction_lock_exhaustion_precedent(db_manager):
    query = "requests post inside db begin transaction lock external network call pool exhaustion"
    result = db_manager.search_precedents_by_text(query, top_k=2, min_similarity=0.75)

    assert len(result.matched_precedents) > 0
    top_precedent = result.matched_precedents[0]
    assert top_precedent.bug_category == "TRANSACTION_LOCK_EXHAUSTION"
    assert "AST-FIN-003" in result.elevated_rules


def test_unrelated_content_returns_zero_precedents(db_manager):
    # Irrelevant content should not meet the 0.78 similarity threshold
    irrelevant_query = "recipe for chocolate fudge brownies with vanilla bean ice cream"
    result = db_manager.search_precedents_by_text(irrelevant_query, top_k=3, min_similarity=0.78)

    assert len(result.matched_precedents) == 0
    assert len(result.elevated_rules) == 0


# --- 4. Dynamic Rule Weighting & Correlation ---

def test_dynamic_rule_weight_updates(db_manager):
    rule = db_manager.get_rule("AST-FIN-001")
    assert rule is not None
    assert rule.current_weight == 1.5
    assert rule.revert_count == 0

    # Increase weight after production flakiness
    db_manager.update_rule_weight("AST-FIN-001", new_weight=2.8, ci_correlation=0.65, increment_reverts=True)
    updated = db_manager.get_rule("AST-FIN-001")
    assert updated.current_weight == 2.8
    assert updated.ci_flakiness_correlation == 0.65
    assert updated.revert_count == 1

    # Bounds enforcement: cannot exceed 5.0 or drop below 0.2
    db_manager.update_rule_weight("AST-FIN-001", new_weight=10.0)
    assert db_manager.get_rule("AST-FIN-001").current_weight == 5.0

    db_manager.update_rule_weight("AST-FIN-001", new_weight=0.01)
    assert db_manager.get_rule("AST-FIN-001").current_weight == 0.2


# --- 5. Wire-Speed Latency Benchmark ---

def test_wire_speed_vector_search_latency(db_manager):
    query = "Concurrent withdrawal debit race condition balance below zero"
    result = db_manager.search_precedents_by_text(query, top_k=3)
    # SLA: Sub-25ms vector retrieval
    assert result.query_duration_ms < 25.0, f"Query took {result.query_duration_ms}ms, expected < 25ms"
