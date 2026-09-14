"""
FinGuard Tier 5: Bayesian Rule Weight Optimizer
Dynamically tunes institutional review rule priorities based on post-deploy reverts, CI flakiness, and developer feedback.
"""
from typing import Optional, Dict, Any
from app.telemetry.models import TelemetryEvent, TelemetryEventType, RuleWeightUpdateResult
from app.telemetry.ledger import LearningLedgerManager
from app.database.manager import DatabaseManager

MIN_RULE_WEIGHT = 0.2  # Strict safety floor (NEW-02 & SG-05)
MAX_RULE_WEIGHT = 5.0  # Strict ceiling
DEFAULT_ALPHA = 0.15   # Learning rate


class BayesianRuleOptimizer:
    """
    Applies closed-loop Bayesian adjustments to review rule priorities.
    Ensures safety-critical rules maintain minimum floor W_i >= 0.2 regardless of developer dismissals.
    """

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        ledger_manager: Optional[LearningLedgerManager] = None,
        alpha: float = DEFAULT_ALPHA
    ):
        self.db_manager = db_manager or DatabaseManager(backend="sqlite")
        self.ledger_manager = ledger_manager or LearningLedgerManager()
        self.alpha = alpha

    def process_event(self, event: TelemetryEvent) -> RuleWeightUpdateResult:
        """
        Ingests a telemetry event, calculates Bayesian delta, updates database and ledger.
        """
        rule = self.db_manager.get_rule(event.rule_id)
        current_weight = rule.current_weight if rule else 1.0

        revert_incremented = False
        new_ci_correlation = None

        if event.event_type == TelemetryEventType.POST_DEPLOY_REVERT:
            # Code suffered a revert in production -> elevate rule priority
            delta = self.alpha * 2.0
            new_weight = min(MAX_RULE_WEIGHT, current_weight + delta)
            revert_incremented = True
            msg = f"Rule priority elevated due to post-deploy git revert in {event.repo_name}"

        elif event.event_type == TelemetryEventType.CI_BUILD_FLAKINESS:
            # CI transaction integration test failed or flaked
            delta = self.alpha * 1.0
            new_weight = min(MAX_RULE_WEIGHT, current_weight + delta)
            new_ci_correlation = min(1.0, (rule.ci_flakiness_correlation if rule else 0.0) + 0.1)
            msg = "Rule priority adjusted after CI flakiness correlation"

        elif event.event_type == TelemetryEventType.DEV_ACCEPTED_PATCH:
            # Developer accepted and merged the synthesized one-click patch
            delta = self.alpha * 0.5
            new_weight = min(MAX_RULE_WEIGHT, current_weight + delta)
            msg = "Rule confidence reinforced by accepted one-click patch"

        elif event.event_type == TelemetryEventType.DEV_REJECTED_FINDING:
            # Developer dismissed the finding as false positive -> lower weight with strict floor
            delta = -(self.alpha * 0.8)
            new_weight = max(MIN_RULE_WEIGHT, current_weight + delta)
            msg = f"Rule priority decayed after developer dismissal (bounded by floor {MIN_RULE_WEIGHT})"

        else:
            delta = 0.0
            new_weight = current_weight
            msg = "No adjustment for unknown event type"

        new_weight = round(new_weight, 4)

        # 1. Update Database (Cloud SQL or Local SQLite)
        self.db_manager.update_rule_weight(
            rule_id=event.rule_id,
            new_weight=new_weight,
            ci_correlation=new_ci_correlation,
            increment_reverts=revert_incremented
        )

        # 2. Update Learning Ledger
        self.ledger_manager.update_rule_weight(
            rule_id=event.rule_id,
            new_weight=new_weight
        )

        return RuleWeightUpdateResult(
            event_id=event.id,
            rule_id=event.rule_id,
            previous_weight=current_weight,
            updated_weight=new_weight,
            delta=round(new_weight - current_weight, 4),
            event_type=event.event_type.value,
            revert_incremented=revert_incremented,
            message=msg
        )
