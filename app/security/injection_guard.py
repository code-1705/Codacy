"""
FinGuard Tier 1: Adversarial Prompt Injection Guard
Detects and quarantines prompt injection attempts disguised in code comments, strings, or docstrings.
"""
import re
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass(frozen=True)
class InjectionCheckResult:
    is_quarantined: bool
    reason: Optional[str]
    matched_pattern: Optional[str]
    severity: str = "CLEAN"


class InjectionGuard:
    """Detects control hijacking and prompt injection attacks in untrusted code."""

    # High-confidence adversarial injection patterns (case-insensitive)
    INJECTION_PATTERNS: List[Tuple[str, str, str]] = [
        # (Pattern regex, Reason, Severity)
        (
            r"(?i)\bignore\s+(all\s+)?previous\s+instructions\b",
            "Prompt injection: Attempt to override system instructions",
            "CRITICAL"
        ),
        (
            r"(?i)\bdisregard\s+(all\s+)?prior\s+(prompts?|instructions?|rules?)\b",
            "Prompt injection: Attempt to disregard prior rules",
            "CRITICAL"
        ),
        (
            r"(?i)\bsystem\s+override\b",
            "Prompt injection: System override directive",
            "CRITICAL"
        ),
        (
            r"(?i)\b(dan\s+mode|do\s+anything\s+now)\s+(enabled|activated)?\b",
            "Prompt injection: Jailbreak persona activation (DAN mode)",
            "CRITICAL"
        ),
        (
            r"(?i)\byou\s+are\s+now\s+(in\s+developer\s+mode|unrestricted)\b",
            "Prompt injection: Developer mode jailbreak attempt",
            "CRITICAL"
        ),
        (
            r"(?i)<\s*(system|instructions?|prompt|system_override)\s*>",
            "Prompt injection: XML control tag hijacking attempt",
            "CRITICAL"
        ),
        (
            r"(?i)\b(always\s+approve|no\s+vulnerabilities\s+found|bypass\s+all\s+checks|mark\s+as\s+clean)\b.*(code\s+review|finguard|reviewer)",
            "Prompt injection: Attempt to coerce reviewer approval",
            "HIGH"
        ),
        (
            r"(?i)assistant\s*:\s*(i\s+approve|no\s+bugs|verified\s+clean)",
            "Prompt injection: Fake assistant response injection",
            "CRITICAL"
        )
    ]

    def __init__(self):
        self._compiled_patterns = [
            (re.compile(pattern), reason, severity)
            for pattern, reason, severity in self.INJECTION_PATTERNS
        ]

    def inspect(self, content: str) -> InjectionCheckResult:
        """
        Inspect untrusted content for prompt injection payloads.
        Returns InjectionCheckResult with is_quarantined=True if an attack is detected.
        """
        if not content:
            return InjectionCheckResult(is_quarantined=False, reason=None, matched_pattern=None)

        for regex, reason, severity in self._compiled_patterns:
            match = regex.search(content)
            if match:
                return InjectionCheckResult(
                    is_quarantined=True,
                    reason=f"{reason} (matched: '{match.group(0)}')",
                    matched_pattern=match.group(0),
                    severity=severity
                )

        return InjectionCheckResult(
            is_quarantined=False,
            reason=None,
            matched_pattern=None,
            severity="CLEAN"
        )
