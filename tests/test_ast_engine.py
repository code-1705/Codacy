"""
Unit Tests for FinGuard Tier 0: Token-Free AST Engine
Validates deterministic detection of FinTech anti-patterns at wire speed (<15ms).
"""
import pytest
from app.ast_engine.analyzer import ASTAnalyzer, ASTAnalysisResult
from app.ast_engine.rules import AST_FINTECH_RULES


@pytest.fixture
def analyzer():
    return ASTAnalyzer(critical_threshold=3)


# --- 1. Clean Code Baseline ---

def test_clean_financial_code(analyzer):
    code = """
from decimal import Decimal

def calculate_fee(amount: Decimal) -> Decimal:
    rate = Decimal("0.025")
    return amount * rate

def transfer_funds(account_id: str, amount: Decimal):
    if not debit_account(account_id, amount):
        raise ValueError("Insufficient balance")
    credit_account(account_id, amount)
"""
    result = analyzer.analyze_source(code)
    assert result.syntax_valid is True
    assert result.ast_status == "CLEAN"
    assert len(result.deterministic_findings) == 0
    assert result.execution_time_ms < 20.0


# --- 2. Syntax Error Short Circuit ---

def test_syntax_error_short_circuits(analyzer):
    broken_code = """
def process_payment(
    amount: float
    # Missing colon and invalid syntax
"""
    result = analyzer.analyze_source(broken_code)
    assert result.syntax_valid is False
    assert result.ast_status == "SHORT_CIRCUIT_CRITICAL"
    assert len(result.deterministic_findings) == 1
    assert result.deterministic_findings[0]["rule_id"] == "AST-SYNTAX-ERR"
    assert result.llm_token_savings > 0


# --- 3. AST-FIN-001: Float in Currency Arithmetic ---

def test_detects_float_in_currency_calculation(analyzer):
    code = """
def calculate_transaction_fee(amount):
    # Bug: IEEE 754 precision loss using raw float literal
    fee = amount * 0.025
    return fee
"""
    result = analyzer.analyze_source(code)
    assert result.syntax_valid is True
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-001"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "CRITICAL"
    assert "FloatInCurrencyArithmetic" in findings[0]["rule_name"]
    assert "0.025" in findings[0]["message"]


def test_detects_float_cast_in_financial_context(analyzer):
    code = """
def update_user_balance(balance, adjustment):
    new_balance = balance + float(adjustment)
    return new_balance
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-001"]
    assert len(findings) == 1
    assert findings[0]["rule_id"] == "AST-FIN-001"


def test_allows_float_with_inline_suppression(analyzer):
    code = """
def calculate_fee(amount):
    return amount * 0.025  # noqa: AST-FIN-001
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-001"]
    assert len(findings) == 0


# --- 4. AST-FIN-002: Missing Idempotency Key ---

def test_detects_missing_idempotency_in_post_payment_route(analyzer):
    code = """
from fastapi import FastAPI

app = FastAPI()

@app.post("/pay/process")
async def execute_payment(account_id: str, amount: int):
    return {"status": "success"}
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-002"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "HIGH"
    assert "/pay/process" in findings[0]["message"]


def test_passes_route_with_idempotency_key(analyzer):
    code = """
from fastapi import FastAPI, Header

app = FastAPI()

@app.post("/pay/process")
async def execute_payment(account_id: str, amount: int, idempotency_key: str = Header(...)):
    return {"status": "success"}
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-002"]
    assert len(findings) == 0


def test_ignores_non_payment_route(analyzer):
    code = """
from fastapi import FastAPI

app = FastAPI()

@app.get("/users/profile")
async def get_profile(user_id: str):
    return {"user_id": user_id}
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-002"]
    assert len(findings) == 0


# --- 5. AST-FIN-003: Network Call Inside Transaction Lock ---

def test_detects_network_call_in_transaction_block(analyzer):
    code = """
import requests

def settle_order(db, order_id, card_token):
    with db.begin():
        # Critical bug: Network call inside ACID transaction block
        resp = requests.post("https://api.stripe.com/v1/charges", json={"token": card_token})
        db.execute("UPDATE orders SET status = 'paid' WHERE id = :id", {"id": order_id})
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-003"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "CRITICAL"
    assert "requests.post" in findings[0]["message"]


def test_passes_network_call_outside_transaction(analyzer):
    code = """
import requests

def settle_order(db, order_id, card_token):
    # Network call done outside of database transaction lock
    resp = requests.post("https://api.stripe.com/v1/charges", json={"token": card_token})
    
    with db.begin():
        db.execute("UPDATE orders SET status = 'paid' WHERE id = :id", {"id": order_id})
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-003"]
    assert len(findings) == 0


# --- 6. AST-FIN-004: Unchecked Return on Debit ---

def test_detects_unchecked_debit_call(analyzer):
    code = """
def process_withdrawal(account, amount):
    # Bug: Return value of debit is ignored, balance can go negative
    account.debit(amount)
    send_receipt(account.id)
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-004"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "CRITICAL"


def test_passes_checked_debit_call(analyzer):
    code = """
def process_withdrawal(account, amount):
    if not account.debit(amount):
        raise ValueError("Insufficient balance")
    send_receipt(account.id)
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-004"]
    assert len(findings) == 0


def test_passes_debit_in_try_block(analyzer):
    code = """
def process_withdrawal(account, amount):
    try:
        account.debit(amount)
    except InsufficientBalanceError:
        logger.error("Failed debit")
        return False
    return True
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-004"]
    assert len(findings) == 0


def test_detects_float_augmented_assignment(analyzer):
    code = """
def update_balance(current_balance):
    current_balance += 10.5
    return current_balance
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-001"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "CRITICAL"
    assert findings[0]["category"] == "LEDGER_INTEGRITY"


def test_detects_async_unchecked_debit(analyzer):
    code = """
async def process_withdrawal(account, amount):
    # Bug: Awaited debit call return value discarded without error handling
    await account.debit(amount)
    await notify_user(account.id)
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-004"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "CRITICAL"
    assert findings[0]["category"] == "LEDGER_INTEGRITY"


def test_detects_missing_idempotency_with_keyword_path(analyzer):
    code = """
from fastapi import FastAPI

app = FastAPI()

@app.post(path="/pay/v2/execute")
async def execute_payment(account_id: str, amount: int):
    return {"status": "success"}
"""
    result = analyzer.analyze_source(code)
    findings = [f for f in result.deterministic_findings if f["rule_id"] == "AST-FIN-002"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "HIGH"
    assert findings[0]["category"] == "IDEMPOTENCY"


# --- 7. Multi-Violation Short Circuit ---

def test_multiple_critical_flaws_triggers_short_circuit(analyzer):
    code = """
import requests

def calculate_fee_and_pay(db, order_id, amount):
    fee = amount * 0.05
    with db.begin():
        requests.post("https://gateway.com/charge")
    account.debit(amount)
"""
    result = analyzer.analyze_source(code)
    assert result.ast_status == "SHORT_CIRCUIT_CRITICAL"
    assert len(result.deterministic_findings) >= 3
    assert result.llm_token_savings > 0


# --- 8. Diff Extraction & Wire-Speed Execution ---

def test_diff_analyzer(analyzer):
    diff = """
--- a/billing.py
+++ b/billing.py
@@ -10,3 +10,4 @@
 def calculate_tax(subtotal):
+    rate = 0.18
+    return subtotal * rate
"""
    result = analyzer.analyze_diff(diff)
    assert result.syntax_valid is True
    assert len(result.deterministic_findings) > 0
    assert result.deterministic_findings[0]["rule_id"] == "AST-FIN-001"


def test_analyze_file(tmp_path, analyzer):
    test_file = tmp_path / "ledger_service.py"
    test_file.write_text("""
def calculate_interest(principal):
    return principal * 0.07
""", encoding="utf-8")

    result = analyzer.analyze_file(str(test_file))
    assert result.syntax_valid is True
    assert len(result.deterministic_findings) == 1
    assert result.deterministic_findings[0]["rule_id"] == "AST-FIN-001"


def test_wire_speed_benchmark_1000_lines(analyzer):
    # Construct realistic 1000 lines of Python code
    chunk = """def process_entry_{i}(account_id: str, balance: int):
    status = "OK"
    if balance < 0:
        return False
    return True"""
    raw_code = "\n".join(chunk.format(i=i) for i in range(200))
    large_code = "\n".join(raw_code.splitlines()[:1000])
    assert len(large_code.splitlines()) == 1000

    # Best-of-3 runs to account for OS scheduling noise on Windows
    runs = [analyzer.analyze_source(large_code) for _ in range(3)]
    best_result = min(runs, key=lambda r: r.execution_time_ms)
    assert best_result.syntax_valid is True
    assert best_result.ast_status == "CLEAN"
    # Wire speed assertion: 1000 lines must complete in < 25ms (<10ms on Linux Cloud Run)
    assert best_result.execution_time_ms < 25.0, f"Best execution took {best_result.execution_time_ms}ms, expected < 25ms"




def test_rule_metadata_registry():
    assert "AST-FIN-001" in AST_FINTECH_RULES
    assert "AST-FIN-002" in AST_FINTECH_RULES
    assert "AST-FIN-003" in AST_FINTECH_RULES
    assert "AST-FIN-004" in AST_FINTECH_RULES
    for rule_id, rule in AST_FINTECH_RULES.items():
        assert rule.id == rule_id
        assert rule.severity in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        assert len(rule.description) > 0
