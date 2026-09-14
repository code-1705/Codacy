"""
Unit Tests for FinGuard Tier 4: Sandboxed Repro & Fix Verification Engine
Validates unified diff patching, repro test synthesis, and the 3-phase verification lifecycle.
"""
import pytest
from app.sandbox.patcher import apply_patch, PatchApplicationError
from app.sandbox.synthesizer import ReproSynthesizer
from app.sandbox.runner import EphemeralSandboxRunner
from app.sandbox.models import VerificationResult


# --- 1. In-Memory Unified Diff Patcher ---

def test_apply_patch_cleanly_modifies_code():
    original = """def calculate_fee(amount):
    return amount * 0.05
"""
    patch = """--- a/service.py
+++ b/service.py
@@ -1,2 +1,3 @@
 def calculate_fee(amount):
-    return amount * 0.05
+    from decimal import Decimal
+    return Decimal(str(amount)) * Decimal("0.05")
"""
    patched = apply_patch(original, patch)
    assert "from decimal import Decimal" in patched
    assert "Decimal(str(amount))" in patched
    assert "amount * 0.05" not in patched


def test_apply_patch_raises_on_unmatchable_diff():
    original = "x = 42\n"
    invalid_patch = """--- a/service.py
+++ b/service.py
@@ -50,2 +50,2 @@
-def non_existent_function():
+def modified_function():
"""
    with pytest.raises(PatchApplicationError):
        apply_patch(original, invalid_patch)


# --- 2. Repro Test Synthesizer ---

def test_repro_synthesizer_generates_targeted_tests():
    # Race condition synthesis
    script_race, err_race = ReproSynthesizer.synthesize_repro("RACE_CONDITION")
    assert "concurrent.futures" in script_race
    assert "test_concurrent_withdrawal_race" in script_race
    assert "Balance dropped below zero" in err_race

    # Idempotency synthesis
    script_idem, err_idem = ReproSynthesizer.synthesize_repro("IDEMPOTENCY")
    assert "idempotency_key" in script_idem
    assert "Duplicate transaction" in err_idem

    # Float drift synthesis
    script_float, err_float = ReproSynthesizer.synthesize_repro("FLOAT_PRECISION_DRIFT")
    assert "Decimal" in script_float
    assert "Raw float returned" in err_float


# --- 3. Complete 3-Phase Verification Lifecycle ---

def test_sandbox_verification_lifecycle_success():
    """
    Validates complete 3-phase protocol:
    Phase 1: Vulnerable balance check fails under concurrent load.
    Phase 2: Patch applies mutex lock.
    Phase 3: Patched balance check passes.
    """
    vulnerable_service = """import time
import threading

class Account:
    def __init__(self, balance=100):
        self.balance = balance
        self._lock = threading.Lock()

    def withdraw(self, amount):
        if self.balance >= amount:
            time.sleep(0.01)
            self.balance -= amount
            return True
        return False
"""

    patch = """--- a/service.py
+++ b/service.py
@@ -9,5 +9,7 @@
     def withdraw(self, amount):
-        if self.balance >= amount:
-            time.sleep(0.01)
-            self.balance -= amount
-            return True
+        with self._lock:
+            if self.balance >= amount:
+                time.sleep(0.01)
+                self.balance -= amount
+                return True
         return False
"""

    repro_test = """import pytest
import concurrent.futures
from service import Account

def test_concurrent_withdrawal_race():
    acc = Account(balance=100)
    def attempt(amt):
        return acc.withdraw(amt)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt, 30) for _ in range(5)]
        results = [f.result() for f in futures]

    # Invariant: balance must never be negative
    assert acc.balance >= 0, f"Balance dropped negative: {acc.balance}"
"""

    runner = EphemeralSandboxRunner(timeout_sec=4.0)
    result = runner.verify(
        code_before=vulnerable_service,
        repro_script=repro_test,
        patch_diff=patch
    )

    assert result.phase_1_baseline_failed is True
    assert result.phase_2_patch_applied is True
    assert result.phase_3_post_patch_passed is True
    assert result.verification_status == "PASSED"
    assert "FAILED" in result.baseline_failure_output or "assert" in result.baseline_failure_output.lower()
    assert result.execution_time_ms < 3500.0  # Well below 4.0s SLA


def test_sandbox_detects_failed_to_reproduce():
    """If original code already passes, verification must flag FAILED_TO_REPRODUCE."""
    sound_service = """class Account:
    def __init__(self, balance=100):
        self.balance = balance
    def withdraw(self, amount):
        return True
"""
    repro_test = """from service import Account
def test_always_passes():
    acc = Account(100)
    assert acc.balance == 100
"""
    runner = EphemeralSandboxRunner(timeout_sec=2.0)
    result = runner.verify(
        code_before=sound_service,
        repro_script=repro_test,
        patch_diff=""
    )

    assert result.verification_status == "FAILED_TO_REPRODUCE"
    assert result.phase_1_baseline_failed is False


def test_sandbox_detects_invalid_patch():
    """If patch fails to remedy the bug, status must be FAILED."""
    broken_service = """def compute(): return 0"""
    bad_patch = """--- a/service.py
+++ b/service.py
@@ -1,1 +1,1 @@
-def compute(): return 0
+def compute(): return 1
"""
    repro_test = """from service import compute
def test_must_be_two():
    assert compute() == 2
"""
    runner = EphemeralSandboxRunner(timeout_sec=2.0)
    result = runner.verify(
        code_before=broken_service,
        repro_script=repro_test,
        patch_diff=bad_patch
    )

    assert result.phase_1_baseline_failed is True
    assert result.phase_2_patch_applied is True
    assert result.phase_3_post_patch_passed is False
    assert result.verification_status == "FAILED"


def test_sandbox_enforces_execution_timeout():
    """Subprocess runner enforces max timeout constraint."""
    hanging_service = """def hang(): pass"""
    hanging_test = """import time
def test_sleep_forever():
    time.sleep(5.0)
"""
    runner = EphemeralSandboxRunner(timeout_sec=0.5)
    passed, output, elapsed_ms = runner._execute_in_tempdir(
        service_code=hanging_service,
        test_code=hanging_test
    )

    assert passed is False
    assert "TimeoutExpired" in output
    assert elapsed_ms < 1500.0
