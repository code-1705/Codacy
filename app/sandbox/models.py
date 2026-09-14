"""
FinGuard Tier 4: Sandbox & Verification Models
Enforces structured result contracts for sandboxed repro execution and patch verification.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any


@dataclass
class VerificationResult:
    """
    Complete audit result of the 3-phase verification lifecycle:
    Phase 1: Proof of Bug (Must Fail)
    Phase 2: Patch Application
    Phase 3: Proof of Fix (Must Pass)
    """
    verification_status: str  # "PASSED" | "FAILED" | "FAILED_TO_REPRODUCE" | "UNVERIFIABLE"
    phase_1_baseline_failed: bool
    phase_2_patch_applied: bool
    phase_3_post_patch_passed: bool
    baseline_failure_output: str = ""
    post_patch_output: str = ""
    execution_time_ms: float = 0.0
    patch_diff: str = ""
    repro_script: str = ""
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
