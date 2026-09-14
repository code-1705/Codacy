"""
FinGuard Tier 5: Learning Ledger Manager
Maintains institutional memory, feedback logs, and rolling pilot KPIs in .finguard/learning_ledger.json.
"""
import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

DEFAULT_LEDGER_PATH = ".finguard/learning_ledger.json"


class LearningLedgerManager:
    """Manages reading, updating, and syncing the institutional learning ledger."""

    def __init__(self, ledger_path: str = DEFAULT_LEDGER_PATH):
        self.ledger_path = ledger_path
        self._ensure_ledger_exists()

    def _ensure_ledger_exists(self):
        dir_name = os.path.dirname(self.ledger_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        if not os.path.exists(self.ledger_path):
            initial_data = {
                "system": "FinGuard - FinTech Verifiable Code Review Engine",
                "hackathon_track": "AIM Code Kitchen S01 - Track 1",
                "version": "1.0.0",
                "pilot_baseline": {
                    "median_review_time_hours": 48.0,
                    "revert_rate_pct": 8.4,
                    "target_median_review_time_hours": 24.0,
                    "stretch_target_review_seconds": 30.0,
                    "target_revert_reduction_pct": 60.0
                },
                "retrospective_entries": [],
                "tuned_rule_weights": {}
            }
            with open(self.ledger_path, "w", encoding="utf-8") as f:
                json.dump(initial_data, f, indent=2)

    def load_ledger(self) -> Dict[str, Any]:
        """Loads current state of the learning ledger."""
        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_ledger(self, data: Dict[str, Any]):
        """Persists updated state to learning_ledger.json."""
        with open(self.ledger_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def update_rule_weight(self, rule_id: str, new_weight: float):
        """Updates the tuned_rule_weights section in the ledger."""
        data = self.load_ledger()
        if "tuned_rule_weights" not in data:
            data["tuned_rule_weights"] = {}
        data["tuned_rule_weights"][rule_id] = round(new_weight, 4)
        self.save_ledger(data)

    def append_retrospective_entry(
        self,
        entry_id: str,
        agent: str,
        phase: str,
        event_type: str,
        summary: str,
        action_items: Optional[List[str]] = None
    ):
        """Appends a new retrospective self-correction entry."""
        data = self.load_ledger()
        if "retrospective_entries" not in data:
            data["retrospective_entries"] = []

        entry = {
            "id": entry_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "phase": phase,
            "event_type": event_type,
            "summary": summary,
            "action_items": action_items or []
        }
        data["retrospective_entries"].append(entry)
        self.save_ledger(data)

    def get_kpis(self) -> Dict[str, Any]:
        """Returns pilot performance metrics and reduction progress."""
        data = self.load_ledger()
        baseline = data.get("pilot_baseline", {})
        return {
            "baseline_median_hours": baseline.get("median_review_time_hours", 48.0),
            "current_target_hours": baseline.get("target_median_review_time_hours", 24.0),
            "stretch_target_seconds": baseline.get("stretch_target_review_seconds", 30.0),
            "baseline_revert_pct": baseline.get("revert_rate_pct", 8.4),
            "target_revert_reduction_pct": baseline.get("target_revert_reduction_pct", 60.0)
        }
