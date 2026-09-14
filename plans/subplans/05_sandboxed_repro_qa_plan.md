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

> [!IMPORTANT FIX — NEW-03 & HYB-04]
> "Container **or** subprocess" was an unacceptable ambiguity, and Cloud Run service instances cannot run nested Docker daemons. The sandboxed execution runner detects its execution context and applies strict multi-tier isolation:
>
> **Context 1: Cloud Run Hosted Gateway (Deliverable #1)**
> * **Primary (Cloud Run Jobs API):** Triggers an ephemeral Google Cloud Run Job task with a specialized `finguard-repro-runner` container (`--network none`, 256MiB limit, 5s timeout).
> * **Fallback (Cloud Run In-Process Restricted Runner):** If Cloud Run Jobs dispatch is disabled, runs within an isolated tempdir using resource limits (`resource.setrlimit(RLIMIT_CPU, 4)` and `RLIMIT_AS`), namespace isolation, and strict process termination.
>
> **Context 2: Local Developer CLI / CI Workstation**
> * **Tier A (Preferred — Local Docker):** Spins up an ephemeral `python:3.11-slim` Docker container per review (`--network none`, read-only host mount, memory capped at 256MB). Destroyed immediately upon completion.
> * **Tier B (Fallback — `seccomp`-Restricted Subprocess):** Used when Docker daemon is not running locally. Mandatory constraints:
>   * `seccomp` profile / restricted syscall filter blocking `socket()`, `unlink()`, and unauthorized writes.
>   * Execution timeout: max **4.0 seconds**.
>   * Memory cap: **256MB** via `resource.setrlimit`.
>   * Read-only isolated working directory.
> * If neither Tier A nor Tier B can be satisfied, sandbox execution is **ABORTED** and marked `verification_status: UNVERIFIABLE`.

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
