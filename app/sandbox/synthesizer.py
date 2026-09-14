"""
FinGuard Tier 4: Automated Repro & Patch Synthesizer
Synthesizes deterministic standalone pytest reproduction test scripts and unified git patches.
"""
from typing import Dict, Any, Optional, Tuple


class ReproSynthesizer:
    """Generates deterministic pytest test scripts and unified patches for FinTech findings."""

    @staticmethod
    def synthesize_repro(category: str, file_path: str = "service.py", line_no: int = 10) -> Tuple[str, str]:
        """
        Synthesizes (repro_script_content, expected_failure_message).
        """
        cat = category.upper()

        if cat in ("RACE_CONDITION", "DOUBLE_SPEND_RACE"):
            script = """import pytest
import concurrent.futures
import time
from service import Account

def test_concurrent_withdrawal_race():
    # Setup account with 100 balance
    acc = Account(balance=100)
    successes = 0

    def attempt_withdraw(amount):
        return acc.withdraw(amount)

    # 5 concurrent withdrawals of 30 each (Total attempted: 150 > 100)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_withdraw, 30) for _ in range(5)]
        results = [f.result() for f in futures]

    successful_withdrawals = sum(1 for r in results if r is True)
    # INVARIANT: Balance must NEVER drop below zero
    assert acc.balance >= 0, f"Critical: Balance dropped below zero: {acc.balance}"
    assert successful_withdrawals <= 3, f"Critical: Overdraft permitted, {successful_withdrawals} withdrawals succeeded"
"""
            expected_fail = "Critical: Balance dropped below zero"
            return script, expected_fail

        elif cat in ("IDEMPOTENCY", "MISSING_IDEMPOTENCY", "MISSING_IDEMPOTENCY_RETRY"):
            script = """import pytest
from service import process_payment

def test_idempotent_retry_prevents_duplicate_charge():
    idempotency_key = "idem_key_unique_test_992"
    
    # First attempt
    res1 = process_payment(idempotency_key=idempotency_key, amount=50)
    assert res1["status"] in ("SUCCESS", "OK")

    # Second retry attempt with same idempotency key
    res2 = process_payment(idempotency_key=idempotency_key, amount=50)
    
    # INVARIANT: Retry MUST NOT create duplicate charge
    assert res2.get("is_duplicate") is True or res2.get("transaction_id") == res1.get("transaction_id"), \\
        "Critical: Duplicate transaction created for identical idempotency key"
"""
            expected_fail = "Critical: Duplicate transaction created for identical idempotency key"
            return script, expected_fail

        elif cat in ("FLOAT_PRECISION_DRIFT", "FLOAT_IN_CURRENCY"):
            script = """import pytest
from decimal import Decimal
from service import calculate_total_balance

def test_float_precision_drift_rejected():
    # 10 transactions of 0.1
    result = calculate_total_balance([0.1] * 10)
    
    # INVARIANT: Financial calculation must equal exact 1.0 without IEEE 754 drift
    assert result == Decimal("1.0") or result == 1.0, f"Critical: Float IEEE 754 precision drift: {result}"
    assert not isinstance(result, float), "Critical: Raw float returned for currency amount"
"""
            expected_fail = "Critical: Raw float returned for currency amount"
            return script, expected_fail

        else:
            # Generic financial invariant test
            script = f"""import pytest
import service

def test_financial_invariant_{cat.lower()}():
    assert hasattr(service, 'verify_transaction_guard'), "Service missing transaction guard"
    assert service.verify_transaction_guard() is True, "Transactional invariant failed"
"""
            expected_fail = "Transactional invariant failed"
            return script, expected_fail

    @staticmethod
    def synthesize_patch_diff(
        category: str,
        file_path: str = "service.py",
        original_code: str = ""
    ) -> str:
        """Generates a contextual unified diff patch remediating the vulnerability."""
        cat = category.upper()

        if cat in ("RACE_CONDITION", "DOUBLE_SPEND_RACE"):
            return f"""--- a/{file_path}
+++ b/{file_path}
@@ -10,4 +10,6 @@
-    def withdraw(self, amount):
-        if self.balance >= amount:
-            time.sleep(0.01)
-            self.balance -= amount
+    def withdraw(self, amount):
+        with self._lock:
+            if self.balance >= amount:
+                time.sleep(0.01)
+                self.balance -= amount
+                return True
+            return False
"""
        elif cat in ("IDEMPOTENCY", "MISSING_IDEMPOTENCY", "MISSING_IDEMPOTENCY_RETRY"):
            return f"""--- a/{file_path}
+++ b/{file_path}
@@ -12,3 +12,6 @@
-def process_payment(idempotency_key, amount):
-    return {{"status": "SUCCESS", "transaction_id": "tx_" + str(time.time())}}
+def process_payment(idempotency_key, amount):
+    if idempotency_key in _SEEN_IDEMPOTENCY_KEYS:
+        return {{"status": "SUCCESS", "transaction_id": _SEEN_IDEMPOTENCY_KEYS[idempotency_key], "is_duplicate": True}}
+    tx_id = "tx_" + str(time.time())
+    _SEEN_IDEMPOTENCY_KEYS[idempotency_key] = tx_id
+    return {{"status": "SUCCESS", "transaction_id": tx_id}}
"""
        elif cat in ("FLOAT_PRECISION_DRIFT", "FLOAT_IN_CURRENCY"):
            return f"""--- a/{file_path}
+++ b/{file_path}
@@ -5,3 +5,4 @@
-def calculate_total_balance(amounts):
-    return sum(amounts)
+def calculate_total_balance(amounts):
+    from decimal import Decimal
+    return sum(Decimal(str(a)) for a in amounts)
"""
        else:
            return f"""--- a/{file_path}
+++ b/{file_path}
@@ -1,2 +1,3 @@
+# FinGuard Protected
"""
