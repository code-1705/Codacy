"""
FinGuard Quality Rating Engine
Calculates standardized 1 to 10 code quality score based on defect severity and frequency.
Satisfies Track 1 mandate: Standardized Code Quality Rating on a scale of 1 to 10.
"""
from typing import List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class QualityRating:
    score: float  # 1.0 to 10.0
    grade: str    # "A+", "A", "B", "C", "F"
    verdict: str  # Human readable summary
    critical_defects: int
    high_defects: int
    medium_defects: int
    low_defects: int
    penalty_points: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_quality_rating(findings: List[Dict[str, Any]]) -> QualityRating:
    """
    Computes a standardized code quality rating on a 1.0 to 10.0 scale.
    Base score: 10.0
    Deductions:
      - CRITICAL: -2.5 per defect (race condition, secret leak, double-spend)
      - HIGH: -1.5 per defect (missing idempotency, precision loss)
      - MEDIUM: -0.8 per defect (unhandled error, performance warning)
      - LOW / AUDIT_NOTE: -0.3 per defect
    Clamped strictly between 1.0 and 10.0.
    """
    crit_count = 0
    high_count = 0
    med_count = 0
    low_count = 0

    for f in findings:
        sev = str(f.get("severity", "")).upper()
        if sev == "CRITICAL":
            crit_count += 1
        elif sev == "HIGH":
            high_count += 1
        elif sev == "MEDIUM":
            med_count += 1
        else:
            low_count += 1

    total_penalty = (
        (crit_count * 2.5) +
        (high_count * 1.5) +
        (med_count * 0.8) +
        (low_count * 0.3)
    )

    raw_score = 10.0 - total_penalty
    final_score = round(max(1.0, min(10.0, raw_score)), 1)

    if final_score >= 9.0:
        grade = "A+" if final_score == 10.0 else "A"
        verdict = "Production Ready: Clean architectural implementation with zero critical defects."
    elif final_score >= 7.5:
        grade = "B"
        verdict = "Minor Optimizations Recommended: Good standard, address low/medium warnings."
    elif final_score >= 5.0:
        grade = "C"
        verdict = "Action Required: Significant transactional or performance concerns detected."
    else:
        grade = "F"
        verdict = "Deployment Blocked: Critical regressions or security vulnerabilities found."

    return QualityRating(
        score=final_score,
        grade=grade,
        verdict=verdict,
        critical_defects=crit_count,
        high_defects=high_count,
        medium_defects=med_count,
        low_defects=low_count,
        penalty_points=round(total_penalty, 2)
    )
