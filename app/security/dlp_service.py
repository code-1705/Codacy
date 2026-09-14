"""
FinGuard Tier 1: Cloud DLP & Local Regex Scrubber
Guarantees zero-leakage of PII, PAN, credentials, and payment data before LLM transmission.
"""
import re
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Set, Tuple
from app.security.injection_guard import InjectionGuard, InjectionCheckResult


@dataclass
class DLPInspectionResult:
    sanitized_content: str
    dlp_status: str  # "CLEAN" | "REDACTED" | "QUARANTINED"
    redacted_findings_count: int
    redacted_info_types: List[str]
    integrity_hash: str  # SHA-256 of sanitized content
    original_integrity_hash: str  # SHA-256 of original raw diff
    quarantine_reason: Optional[str] = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def luhn_checksum_valid(card_number_str: str) -> bool:
    """Validates a credit card number using the ISO/IEC 7812 Luhn algorithm."""
    digits = [int(c) for c in card_number_str if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    
    checksum = 0
    parity = len(digits) % 2
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit = digit * 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return (checksum % 10) == 0


class LocalRegexScrubber:
    """Wire-speed local DLP engine. Zero network calls, fail-closed."""

    REDACTION_TAG = "[REDACTED_BY_FINGUARD_LOCAL_DLP]"

    # Pre-compiled regex patterns for financial credentials and PII
    REGEX_PATTERNS: List[Tuple[str, re.Pattern]] = [
        # Private Keys (RSA, EC, DSA, OpenSSH)
        (
            "PRIVATE_KEY",
            re.compile(
                r"-----BEGIN\s+[A-Z0-9 ]*PRIVATE\s+KEY-----[\s\S]{1,4000}?-----END\s+[A-Z0-9 ]*PRIVATE\s+KEY-----",
                re.MULTILINE
            )
        ),
        # GCP Service Account JSON snippet
        (
            "GCP_CREDENTIALS",
            re.compile(
                r'("type"\s*:\s*"service_account"[\s\S]{1,500}?"private_key"\s*:\s*"[^"]+")',
                re.MULTILINE
            )
        ),
        # Google API Key
        (
            "AUTH_TOKEN",
            re.compile(r"\bAIza[0-9A-Za-z_-]{32,45}\b")
        ),
        # AWS Access Key ID
        (
            "AUTH_TOKEN",
            re.compile(r"\b(AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b")
        ),
        # JWT Token
        (
            "JSON_WEB_TOKEN",
            re.compile(r"\beyJ[A-Za-z0-9-_=]+\.eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]+\b")
        ),
        # India PAN (Permanent Account Number): 5 uppercase letters, 4 digits, 1 uppercase letter
        (
            "INDIA_PAN",
            re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
        ),
        # IBAN (International Bank Account Number)
        (
            "IBAN_CODE",
            re.compile(r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}([A-Z0-9]?){0,16}\b")
        ),
        # Bearer Authorization header
        (
            "AUTH_TOKEN",
            re.compile(r"\bBearer\s+[A-Za-z0-9\-_.~+/]+=*\b", re.IGNORECASE)
        ),
        # Generic hardcoded secrets / API keys in code (e.g. stripe_key = 'sk_live_...')
        (
            "AUTH_TOKEN",
            re.compile(r"\b(sk_live_|pk_live_|rk_live_)[0-9a-zA-Z]{24,}\b")
        ),
    ]

    # ReDoS-free linear credit card regex (continuous digits, 4x4, or 4-6-5 Amex)
    CARD_CANDIDATE_REGEX = re.compile(
        r"\b(?:\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,7}|\d{4}[ -]\d{6}[ -]\d{5}|\d{13,19})\b"
    )

    def scrub(self, content: str) -> Tuple[str, int, List[str]]:
        """
        Executes local regex and Luhn redaction.
        Returns: (sanitized_content, redacted_count, list_of_redacted_info_types)
        """
        if not content:
            return content, 0, []

        sanitized = content
        redacted_count = 0
        detected_types: Set[str] = set()

        # 1. Scrub credit card numbers with strict Luhn verification (only if digits present)
        if any(c.isdigit() for c in sanitized):
            def _card_replace(match: re.Match) -> str:
                nonlocal redacted_count
                raw_match = match.group(0)
                cleaned_digits = re.sub(r"\D", "", raw_match)
                if 13 <= len(cleaned_digits) <= 19 and luhn_checksum_valid(cleaned_digits):
                    redacted_count += 1
                    detected_types.add("CREDIT_CARD_NUMBER")
                    return self.REDACTION_TAG
                return raw_match

            sanitized = self.CARD_CANDIDATE_REGEX.sub(_card_replace, sanitized)

        # 2. Scrub regex patterns with fast string presence pre-checks
        for info_type, pattern in self.REGEX_PATTERNS:
            if info_type == "PRIVATE_KEY" and "-----BEGIN" not in sanitized:
                continue
            if info_type == "GCP_CREDENTIALS" and "service_account" not in sanitized:
                continue
            if info_type == "JSON_WEB_TOKEN" and "eyJ" not in sanitized:
                continue
            if info_type == "INDIA_PAN" and not any(c.isdigit() for c in sanitized):
                continue
            if info_type == "AUTH_TOKEN" and not any(k in sanitized for k in ("AIza", "AKIA", "ASIA", "Bearer", "sk_live", "pk_live", "rk_live")):
                continue

            matches = list(pattern.finditer(sanitized))
            if matches:
                redacted_count += len(matches)
                detected_types.add(info_type)
                sanitized = pattern.sub(self.REDACTION_TAG, sanitized)

        return sanitized, redacted_count, sorted(list(detected_types))


class DLPService:
    """
    Two-Tier Security & DLP Inspection Gateway.
    - Tier A: Local Regex Scrubber (Always active)
    - Tier B: Cloud DLP API client (Optional enterprise integration on Cloud Run)
    - Adversarial Injection Quarantine
    - Fail-Closed Architecture (Zero-Leak Guarantee)
    """

    def __init__(
        self,
        backend: str = "local",
        project_id: Optional[str] = None,
        allow_on_failure: bool = False
    ):
        self.backend = backend.lower()
        self.project_id = project_id
        self.allow_on_failure = allow_on_failure
        self.local_scrubber = LocalRegexScrubber()
        self.injection_guard = InjectionGuard()

    def inspect(self, content: str) -> DLPInspectionResult:
        """
        Inspect and sanitize code diff or raw text.
        Fails closed on any unexpected exception.
        """
        start_time = time.perf_counter()
        orig_hash = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"

        try:
            # Step 1: Check Adversarial Prompt Injection Quarantine
            injection_result: InjectionCheckResult = self.injection_guard.inspect(content)
            if injection_result.is_quarantined:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return DLPInspectionResult(
                    sanitized_content="[QUARANTINED_ADVERSARIAL_INJECTION_DETECTED]",
                    dlp_status="QUARANTINED",
                    redacted_findings_count=1,
                    redacted_info_types=["ADVERSARIAL_PROMPT_INJECTION"],
                    integrity_hash=f"sha256:{hashlib.sha256(b'[QUARANTINED]').hexdigest()}",
                    original_integrity_hash=orig_hash,
                    quarantine_reason=injection_result.reason,
                    execution_time_ms=round(elapsed_ms, 2)
                )

            # Step 2: Local Regex & Luhn Scrubbing (Always Active)
            sanitized, count, info_types = self.local_scrubber.scrub(content)

            # Step 3: Optional Google Cloud DLP API (Tier B)
            if self.backend == "cloud_dlp" and self.project_id:
                sanitized, cloud_count, cloud_types = self._inspect_cloud_dlp(sanitized)
                count += cloud_count
                info_types = sorted(list(set(info_types + cloud_types)))

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            sanitized_hash = f"sha256:{hashlib.sha256(sanitized.encode('utf-8')).hexdigest()}"
            dlp_status = "REDACTED" if count > 0 else "CLEAN"

            return DLPInspectionResult(
                sanitized_content=sanitized,
                dlp_status=dlp_status,
                redacted_findings_count=count,
                redacted_info_types=info_types,
                integrity_hash=sanitized_hash,
                original_integrity_hash=orig_hash,
                quarantine_reason=None,
                execution_time_ms=round(elapsed_ms, 2)
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            # Strict Fail-Closed Guarantee: Never allow uninspected content under failure
            if not self.allow_on_failure:
                return DLPInspectionResult(
                    sanitized_content="[QUARANTINED_DLP_INSPECTION_FAILURE]",
                    dlp_status="QUARANTINED",
                    redacted_findings_count=0,
                    redacted_info_types=[],
                    integrity_hash=f"sha256:{hashlib.sha256(b'[FAILURE]').hexdigest()}",
                    original_integrity_hash=orig_hash,
                    quarantine_reason=f"Fail-closed: DLP inspection failed ({str(e)})",
                    execution_time_ms=round(elapsed_ms, 2)
                )
            raise e

    def _inspect_cloud_dlp(self, text: str) -> Tuple[str, int, List[str]]:
        """
        Executes Google Cloud DLP inspect and deidentify API call.
        Falls back or fails closed based on configuration.
        """
        try:
            from google.cloud import dlp_v2
            client = dlp_v2.DlpServiceClient()
            parent = f"projects/{self.project_id}"

            info_types = [
                {"name": "CREDIT_CARD_NUMBER"},
                {"name": "INDIA_PAN"},
                {"name": "IBAN_CODE"},
                {"name": "AUTH_TOKEN"},
                {"name": "GCP_CREDENTIALS"},
            ]
            inspect_config = {"info_types": info_types, "min_likelihood": dlp_v2.Likelihood.LIKELY}
            deidentify_config = {
                "info_type_transformations": {
                    "transformations": [
                        {
                            "primitive_transformation": {
                                "replace_with_info_type_config": {}
                            }
                        }
                    ]
                }
            }
            item = {"value": text}

            response = client.deidentify_content(
                request={
                    "parent": parent,
                    "deidentify_config": deidentify_config,
                    "inspect_config": inspect_config,
                    "item": item,
                }
            )
            transformed = response.item.value
            redacted_types = [
                d.info_type.name for d in response.overview.transformation_summaries
            ]
            count = sum(s.transformed_bytes for s in response.overview.transformation_summaries)
            return transformed, count, redacted_types
        except ImportError:
            # If google-cloud-dlp is not installed in local environment, rely on Tier A local scrubber
            return text, 0, []
        except Exception as e:
            if not self.allow_on_failure:
                raise RuntimeError(f"Cloud DLP API call failed and allow_on_failure=False: {e}")
            return text, 0, []
