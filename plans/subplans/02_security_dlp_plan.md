# Subplan 02: Cloud DLP & Adversarial Firewall (Tier 1)
**Owner:** `AGENT-SEC-DLP`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope

Prevent PII, credentials, PCI-DSS card data, and malicious prompt injections from reaching Vertex AI or leaking into audit logs.

> **Architecture Shift (Privacy-First CLI Model):**
> FinGuard runs locally. There is no shared cloud endpoint. The DLP engine is the **last gate on the developer's machine** before any bytes are transmitted to Vertex AI. The local regex scrubber is the **primary and always-active** engine. Cloud DLP is an **optional enterprise addon** for teams that want full InfoType coverage and compliance receipts.

## 2. Technical Architecture

### 2.1 Two-Tier DLP Architecture

**Tier A — Local Regex Scrubber (ALWAYS ACTIVE, PRIMARY)**
* Runs 100% offline in <2ms on the developer's machine.
* Zero network calls. Zero billing. Always-on.
* Regex + entropy patterns covering:
  * Credit card numbers (Luhn-validated pattern)
  * Private keys (`-----BEGIN RSA PRIVATE KEY-----`, etc.)
  * GCP service account JSON blobs
  * JWT tokens (`eyJ...`)
  * AWS/GCP access keys (entropy heuristic)
  * India PAN (`[A-Z]{5}[0-9]{4}[A-Z]`)
  * IBAN patterns
* Redaction token: `[REDACTED_BY_FINGUARD_LOCAL_DLP]`.
* **Fail-Closed:** If local scrubber itself errors, the review is aborted. Code never proceeds to Vertex AI.

**Tier B — Google Cloud DLP API (OPTIONAL ENTERPRISE ADDON)**
* Enabled via `.finguard/config.yaml`: `dlp.backend: cloud_dlp`.
* Provides full infoType coverage, compliance receipts, and DPDP audit export.
* Still runs on the sanitized output of Tier A — Belt AND suspenders.
* Disabled by default. Teams with PCI-DSS Level 1 requirements enable this.

### 2.2 Adversarial Prompt Injection Quarantine
* Inspects developer code comments and commit messages for adversarial jailbreak phrases:
  * `IGNORE PREVIOUS INSTRUCTIONS`
  * `SYSTEM OVERRIDE`
  * `DAN MODE ACTIVATED`
  * Embedded `<system>` or `<instructions>` injection attempts.
* Action: Quarantines payload with `QUARANTINE_ADVERSARIAL_INJECTION` and alerts security log.

### 2.3 Cryptographic Integrity
* Generates SHA-256 payload hash of the original and redacted content to provide verifiable audit evidence for Tier 2.

## 3. Interface & Deliverables
* Module: `app/security/dlp_service.py`, `app/security/injection_guard.py`
* Tests: `tests/test_security_dlp.py` validating redaction and injection blocking.
