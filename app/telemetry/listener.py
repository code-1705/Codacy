"""
FinGuard Tier 5: Telemetry Listener & Ingestion Gateway
Receives CI webhooks, GitHub deploy alerts, and developer feedback events.
"""
from typing import Dict, Any, Optional
from app.telemetry.models import TelemetryEvent, RuleWeightUpdateResult
from app.telemetry.optimizer import BayesianRuleOptimizer


class TelemetryListener:
    """Ingests incoming webhook payloads and routes them to the Bayesian optimizer."""

    def __init__(self, optimizer: Optional[BayesianRuleOptimizer] = None):
        self.optimizer = optimizer or BayesianRuleOptimizer()

    def handle_event(self, payload: Dict[str, Any]) -> RuleWeightUpdateResult:
        """
        Parses, validates, and processes incoming telemetry events.
        """
        event = TelemetryEvent(**payload)
        result = self.optimizer.process_event(event)

        # For critical post-deploy reverts, automatically record retrospective learning log
        if event.event_type.value == "POST_DEPLOY_REVERT":
            self.optimizer.ledger_manager.append_retrospective_entry(
                entry_id=f"REVERT-{event.commit_sha[:8]}",
                agent="AGENT-RETRO-LEARN",
                phase="Post-Deploy Incident Analysis",
                event_type="PRODUCTION_REVERT_CORRELATION",
                summary=f"Post-deploy revert on {event.repo_name} (commit {event.commit_sha[:8]}) correlated with rule {event.rule_id}. Weight elevated to {result.updated_weight}.",
                action_items=[
                    f"Prioritize {event.rule_id} in future AST and prompt grounding passes",
                    "Synthesize sandboxed repro regression test"
                ]
            )

        return result
