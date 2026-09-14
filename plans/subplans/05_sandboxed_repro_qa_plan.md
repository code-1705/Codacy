# Subplan 05: Sandboxed Repro QA & Patch Generator (Tier 4)
**Owner:** `AGENT-REPRO-QA`  
**Parent:** [MASTER_IMPLEMENTATION_PLAN.md](file:///c:/Users/Vansh/Desktop/codeKitchenHack/plans/MASTER_IMPLEMENTATION_PLAN.md)

---

## 1. Objectives & Scope
Transform subjective AI commentary into objective, verifiable evidence by synthesizing an executable reproduction test and a verified one-click git patch.

## 2. Technical Architecture

### 2.1 Automated Test Synthesis
* For every critical/high finding, synthesize an executable standalone test (pytest/python) that demonstrates the vulnerability:
  * Race conditions: Multiple concurrent async coroutines or threads executing balance debits.
  * Idempotency bugs: Sending duplicate transaction IDs in loop and asserting multiple ledger mutations occur.
  * Float rounding: Iterating 1,000 transactions with 0.1 increments and asserting IEEE 754 drift.

### 2.2 Ephemeral Execution Runner

> [!IMPORTANT FIX — NEW-03]
> "Container **or** subprocess" was an unacceptable ambiguity. A plain subprocess is NOT isolated from the host filesystem — AI-generated repro code could read `.env`, write temp files, or enumerate directories. The execution hierarchy is now strictly ordered:

**Tier A (Preferred): Ephemeral Container**
* Spins up an isolated `python:3.11-slim` Docker container per review.
* No network access (`--network none`), read-only host filesystem mount, and memory cap (`--memory 256m`).
* Container is destroyed immediately after execution regardless of outcome.

**Tier B (Fallback): `seccomp`-Restricted Subprocess**
* Used only when container runtime is unavailable (e.g. restricted Cloud Run environment).
* Enforces mandatory constraints:
  * `seccomp` profile blocking `open()`, `write()`, `unlink()`, `socket()` syscalls.
  * Execution timeout: max **4.0 seconds**.
  * Memory cap: **256MB** via `resource.setrlimit`.
  * Read-only working directory with `os.chroot()` or equivalent namespace isolation.
* If neither Tier A nor Tier B can be satisfied, sandbox execution is **ABORTED** and the finding is returned without repro verification — marked `verification_status: UNVERIFIABLE`.

**Verification Protocol (unchanged):**
* Phase 1 (Proof of Bug): Runs repro test against original code → **MUST FAIL**.
* Phase 2 (Application of Patch): Applies the unified git diff via `patch` / `git apply`.
* Phase 3 (Proof of Fix): Runs repro test against patched code → **MUST PASS**.

### 2.3 One-Click Patch Delivery
* Outputs valid Unified Diff format ready for immediate developer application:
```diff
--- a/payment/settlement.py
+++ b/payment/settlement.py
@@ -14,3 +14,3 @@
-    cur.execute("SELECT balance FROM accounts WHERE id = %s", (acc_id,))
+    cur.execute("SELECT balance FROM accounts WHERE id = %s FOR UPDATE", (acc_id,))
```

## 3. Interface & Deliverables
* Module: `app/sandbox/runner.py`, `app/sandbox/patcher.py`, `app/sandbox/synthesizer.py`
* Tests: `tests/test_sandbox_runner.py` verifying fail-then-pass lifecycle.
