# Subplan 02: Cloud DLP & Adversarial Firewall (Tier 1)
**Owner:** `AGENT-SEC-DLP`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope

Prevent PII, credentials, PCI-DSS card data, and malicious prompt injections from reaching Vertex AI or leaking into audit logs.

> **Hybrid Privacy & GCP Compliance Model:**
> FinGuard employs a **Dual-Layer DLP Engine**:
> 1. **Client-Side (Local CLI):** The local regex scrubber is always active on the developer's workstation, ensuring no raw credentials or PAN ever cross the wire unredacted.
> 2. **Cloud Tier (Cloud Run Service):** The production service utilizes the **Google Cloud DLP API** (`google-cloud-dlp`) to execute rigorous PCI-DSS and SOC2 infoType inspection (`CREDIT_CARD_NUMBER`, `INDIA_PAN`, `IBAN_CODE`, `AUTH_TOKEN`), certifying review artifacts and consuming GCP sandbox resources compliantly.

## 2. Technical Architecture

### 2.1 Two-Tier DLP Architecture

**Tier A — Local Regex Scrubber (CLIENT-SIDE, ALWAYS ACTIVE)**
* Runs 100% offline in <2ms on the developer's machine inside the CLI / Git Hook.
* Zero network calls. Always-on pre-flight redaction.
* Regex + entropy patterns covering:
  * Credit card numbers (Luhn-validated pattern)
  * Private keys (`-----BEGIN RSA PRIVATE KEY-----`, etc.)
  * GCP service account JSON blobs
  * JWT tokens (`eyJ...`)
  * AWS/GCP access keys (entropy heuristic)
  * India PAN (`[A-Z]{5}[0-9]{4}[A-Z]`)
  * IBAN patterns
* Redaction token: `[REDACTED_BY_FINGUARD_LOCAL_DLP]`.
* **Fail-Closed:** If local scrubber itself errors, the review is aborted. Code never proceeds.

**Tier B — Google Cloud DLP API (CLOUD RUN BACKEND)**
* Deployed on the Cloud Run production service using `google-cloud-dlp`.
* Scans ingested diffs against institutional infoTypes, generating verifiable compliance receipts and cryptographic SHA-256 audit hashes for SOC2/PCI-DSS logs.
* Runs on sanitized streams, validating zero-leakage before Vertex AI prompt construction.

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
