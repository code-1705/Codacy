"""
Unit Tests for FinGuard Tier 5: Telemetry & Bayesian Rule Optimizer
Validates closed-loop feedback, Bayesian priority updates, strict floor/ceiling bounds, and ledger synchronization.
"""
import pytest
from app.telemetry.models import TelemetryEvent, TelemetryEventType
from app.telemetry.optimizer import BayesianRuleOptimizer, MIN_RULE_WEIGHT, MAX_RULE_WEIGHT
from app.telemetry.listener import TelemetryListener
from app.telemetry.ledger import LearningLedgerManager
from app.database.manager import DatabaseManager


@pytest.fixture
def telemetry_setup(tmp_path):
    db_file = str(tmp_path / "test_telemetry_memory.db")
    ledger_file = str(tmp_path / "test_learning_ledger.json")

    db_manager = DatabaseManager(backend="sqlite", sqlite_path=db_file)
    ledger_manager = LearningLedgerManager(ledger_path=ledger_file)
    optimizer = BayesianRuleOptimizer(db_manager=db_manager, ledger_manager=ledger_manager)
    listener = TelemetryListener(optimizer=optimizer)

    return db_manager, ledger_manager, optimizer, listener


# --- 1. Bayesian Weight Adjustment Tests ---

def test_post_deploy_revert_elevates_rule_weight(telemetry_setup):
    db_manager, ledger_manager, optimizer, _ = telemetry_setup

    initial_rule = db_manager.get_rule("AST-FIN-001")
    initial_weight = initial_rule.current_weight
    initial_reverts = initial_rule.revert_count

    event = TelemetryEvent(
        event_type=TelemetryEventType.POST_DEPLOY_REVERT,
        repo_name="org/ledger-service",
        commit_sha="c3d4e5f6a1b27890",
        rule_id="AST-FIN-001",
        details={"reason": "IEEE 754 float drift caused $0.03 ledger imbalance"}
    )

    result = optimizer.process_event(event)

    # Expected: initial_weight + (0.15 * 2.0) = initial_weight + 0.30
    assert result.updated_weight == pytest.approx(initial_weight + 0.30, 0.001)
    assert result.delta > 0
    assert result.revert_incremented is True

    # Verify DB update
    updated_rule = db_manager.get_rule("AST-FIN-001")
    assert updated_rule.current_weight == result.updated_weight
    assert updated_rule.revert_count == initial_reverts + 1

    # Verify Ledger update
    ledger_data = ledger_manager.load_ledger()
    assert ledger_data["tuned_rule_weights"]["AST-FIN-001"] == result.updated_weight


def test_ci_flakiness_adjusts_weight_and_correlation(telemetry_setup):
    db_manager, _, optimizer, _ = telemetry_setup

    initial_rule = db_manager.get_rule("AST-FIN-003")
    initial_weight = initial_rule.current_weight

    event = TelemetryEvent(
        event_type=TelemetryEventType.CI_BUILD_FLAKINESS,
        repo_name="org/settlement",
        commit_sha="d4e5f6a1b2c37890",
        rule_id="AST-FIN-003",
        details={"test_name": "test_settlement_pipeline", "failure": "Connection pool timeout"}
    )

    result = optimizer.process_event(event)

    # Expected: initial_weight + (0.15 * 1.0) = initial_weight + 0.15
    assert result.updated_weight == pytest.approx(initial_weight + 0.15, 0.001)
    updated_rule = db_manager.get_rule("AST-FIN-003")
    assert updated_rule.ci_flakiness_correlation > 0.0


def test_dev_accepted_patch_reinforces_weight(telemetry_setup):
    db_manager, _, optimizer, _ = telemetry_setup

    initial_rule = db_manager.get_rule("AST-FIN-002")
    initial_weight = initial_rule.current_weight

    event = TelemetryEvent(
        event_type=TelemetryEventType.DEV_ACCEPTED_PATCH,
        repo_name="org/payments",
        commit_sha="b2c3d4e5f6a17890",
        rule_id="AST-FIN-002",
        details={"patch_id": "patch_1042", "action": "ONE_CLICK_MERGE"}
    )

    result = optimizer.process_event(event)

    # Expected: initial_weight + (0.15 * 0.5) = initial_weight + 0.075
    assert result.updated_weight == pytest.approx(initial_weight + 0.075, 0.001)


# --- 2. Strict Safety Floor (0.2) and Ceiling (5.0) Bounds ---

def test_dev_rejected_finding_decays_weight_with_strict_floor(telemetry_setup):
    db_manager, _, optimizer, _ = telemetry_setup

    # Consecutive dismissals by developers
    for _ in range(30):
        event = TelemetryEvent(
            event_type=TelemetryEventType.DEV_REJECTED_FINDING,
            repo_name="org/payments",
            commit_sha="feedbeef1234",
            rule_id="AST-FIN-004",
            details={"rationale": "False positive: debit handled in downstream wrapper"}
        )
        result = optimizer.process_event(event)

    # Invariant: NEW-02 & SG-05: Strict safety floor is 0.2, NEVER 0.1 or below!
    assert result.updated_weight == MIN_RULE_WEIGHT
    assert result.updated_weight >= 0.2
    assert db_manager.get_rule("AST-FIN-004").current_weight == 0.2


def test_weight_ceiling_enforced_at_five(telemetry_setup):
    db_manager, _, optimizer, _ = telemetry_setup

    # Consecutive production reverts
    for _ in range(30):
        event = TelemetryEvent(
            event_type=TelemetryEventType.POST_DEPLOY_REVERT,
            repo_name="org/payments",
            commit_sha="deadbeef5678",
            rule_id="RULE-RACE-CONDITION",
            details={"severity": "CRITICAL"}
        )
        result = optimizer.process_event(event)

    # Invariant: Max rule weight ceiling is 5.0
    assert result.updated_weight == MAX_RULE_WEIGHT
    assert db_manager.get_rule("RULE-RACE-CONDITION").current_weight == 5.0


# --- 3. Telemetry Listener & End-to-End Audit Log ---

def test_telemetry_listener_records_retrospective_on_revert(telemetry_setup):
    _, ledger_manager, _, listener = telemetry_setup

    payload = {
        "event_type": "POST_DEPLOY_REVERT",
        "repo_name": "org/wallets",
        "commit_sha": "a1b2c3d4e5f67890",
        "rule_id": "RULE-RACE-CONDITION",
        "details": {"incident_id": "INC-7721", "financial_impact_usd": 12500}
    }

    result = listener.handle_event(payload)
    assert result.updated_weight > result.previous_weight

    # Asserts retrospective learning entry was recorded
    ledger = ledger_manager.load_ledger()
    entries = ledger.get("retrospective_entries", [])
    assert len(entries) > 0

    latest = entries[-1]
    assert "REVERT-a1b2c3d4" in latest["id"]
    assert latest["agent"] == "AGENT-RETRO-LEARN"
    assert "RULE-RACE-CONDITION" in latest["summary"]


# --- 4. Pilot Baseline KPI Metrics ---

def test_pilot_kpi_tracking(telemetry_setup):
    _, ledger_manager, _, _ = telemetry_setup

    kpis = ledger_manager.get_kpis()
    assert kpis["baseline_median_hours"] == 48.0
    assert kpis["current_target_hours"] == 24.0
    assert kpis["stretch_target_seconds"] == 30.0
    assert kpis["baseline_revert_pct"] == 8.4
    assert kpis["target_revert_reduction_pct"] == 60.0
