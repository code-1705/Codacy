"""
FinGuard Tier 0: AST Visitor Engine
Traverses Python AST trees at wire speed (<10ms) to identify deterministic FinTech violations.
"""
import ast
import re
from typing import List, Set, Optional, Dict, Any
from app.ast_engine.rules import (
    DeterministicFinding,
    AST_FINTECH_RULES,
)

# Keywords indicating financial calculations
FINANCIAL_KEYWORDS = {
    "calculate", "fee", "balance", "amount", "interest", "tax", "total",
    "sum", "price", "settle", "payment", "discount", "ledger", "payout",
    "refund", "rate", "charge", "debit", "credit", "currency", "cent",
    "invoice", "transfer", "wallet", "subtotal", "gross", "net"
}

# Mutation route path segments that must require idempotency
IDEMPOTENCY_ROUTE_PREFIXES = (
    "/pay", "/payment", "/transfer", "/settle", "/settlement",
    "/refund", "/charge", "/withdraw", "/deposit", "/checkout",
    "/disburse", "/order", "/billing"
)

# Common network call identifiers
NETWORK_CALL_MODULES = {"requests", "httpx", "urllib", "aiohttp", "urllib3"}
NETWORK_CALL_METHODS = {"get", "post", "put", "patch", "delete", "request", "urlopen"}

# Debit/deduct function patterns
DEBIT_FUNCTION_PATTERNS = {
    "debit", "deduct", "withdraw", "charge_balance", "deduct_balance",
    "decrement_balance", "debit_account", "deduct_funds"
}

# Transaction context manager patterns
TRANSACTION_CONTEXT_NAMES = {
    "begin", "begin_nested", "transaction", "atomic", "start_transaction"
}


class FinTechASTVisitor(ast.NodeVisitor):
    """AST Node Visitor implementing deterministic FinTech verification rules."""

    def __init__(self, file_path: str = "", source_lines: Optional[List[str]] = None, source_code: str = ""):
        self.file_path = file_path
        self._source_code = source_code
        self._source_lines = source_lines
        self.findings: List[DeterministicFinding] = []
        
        # State tracking
        self.current_function_name: Optional[str] = None
        self.is_in_financial_context: bool = False
        self.transaction_depth: int = 0
        self.try_depth: int = 0

    @property
    def source_lines(self) -> List[str]:
        if self._source_lines is None:
            self._source_lines = self._source_code.splitlines() if self._source_code else []
        return self._source_lines

    def _is_financial_name(self, name: Optional[str]) -> bool:
        if not name:
            return False
        lower = name.lower()
        if lower in FINANCIAL_KEYWORDS:
            return True
        return any(kw in lower for kw in FINANCIAL_KEYWORDS)

    def _extract_float_info(self, val_node: ast.AST) -> Optional[str]:
        """Fast path check: returns string representation if node is a float constant or float() call, else None."""
        if isinstance(val_node, ast.Constant):
            if isinstance(val_node.value, float):
                return str(val_node.value)
            return None
        if isinstance(val_node, ast.Call):
            func = val_node.func
            if isinstance(func, ast.Name) and func.id == "float":
                return "float(...)"
        return None

    def _is_suppressed(self, line_num: int, rule_id: str) -> bool:
        """Check if line contains an inline suppression comment (# noqa, # finguard: disable=...)"""
        lines = self.source_lines
        if 0 < line_num <= len(lines):
            line_text = lines[line_num - 1]
            if "noqa" in line_text.lower():
                if rule_id.lower() in line_text.lower() or "noqa" == line_text.strip().lower() or "# noqa" in line_text:
                    return True
            if "finguard: disable" in line_text.lower():
                if rule_id.lower() in line_text.lower() or "all" in line_text.lower():
                    return True
        return False

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_function_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_function_scope(node)

    def _visit_function_scope(self, node: ast.AST):
        prev_func = self.current_function_name
        prev_fin = self.is_in_financial_context

        fn_name = getattr(node, "name", "")
        self.current_function_name = fn_name
        self.is_in_financial_context = self._is_financial_name(fn_name)

        # Check AST-FIN-002: Missing Idempotency Key in mutating payment routes
        self._check_idempotency_guard(node)

        self.generic_visit(node)

        self.current_function_name = prev_func
        self.is_in_financial_context = prev_fin

    def _check_idempotency_guard(self, node: ast.AST):
        """Rule AST-FIN-002: State-mutating routes must enforce an Idempotency-Key."""
        decorators = getattr(node, "decorator_list", [])
        if not decorators:
            return

        is_payment_route = False
        route_path = ""

        for dec in decorators:
            # Match @app.post("/pay"), @router.post("/transfer"), @app.route("/pay", methods=["POST"])
            if isinstance(dec, ast.Call):
                func = dec.func
                func_attr = getattr(func, "attr", "")
                
                # FastAPI / Starlette route methods or Flask @app.route
                is_post_method = func_attr in {"post", "put", "patch"}
                is_route_decorator = func_attr == "route"
                
                # Check path candidates (positional args or path/rule keyword args)
                path_candidates: List[str] = []
                for arg in dec.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        path_candidates.append(arg.value)
                for kw in dec.keywords:
                    if kw.arg in {"path", "rule"} and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        path_candidates.append(kw.value.value)

                for path_val in path_candidates:
                    val = path_val.lower()
                    if any(val.startswith(p) or f"/{p.lstrip('/')}" in val for p in IDEMPOTENCY_ROUTE_PREFIXES):
                        route_path = path_val
                        if is_post_method:
                            is_payment_route = True
                        elif is_route_decorator:
                            # Inspect methods keyword argument
                            for kw in dec.keywords:
                                if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                                    methods = [
                                        el.value.upper() for el in kw.value.elts 
                                        if isinstance(el, ast.Constant) and isinstance(el.value, str)
                                    ]
                                    if any(m in {"POST", "PUT", "PATCH"} for m in methods):
                                        is_payment_route = True

        if is_payment_route:
            # Check function signature for idempotency key presence
            args_obj = getattr(node, "args", None)
            has_idempotency_arg = False

            if args_obj:
                all_args = args_obj.args + args_obj.kwonlyargs
                for a in all_args:
                    arg_name = a.arg.lower()
                    if "idempotenc" in arg_name or "idempotent" in arg_name:
                        has_idempotency_arg = True
                        break

            if not has_idempotency_arg:
                line_start = getattr(node, "lineno", 1)
                line_end = getattr(node, "end_lineno", line_start)
                if not self._is_suppressed(line_start, "AST-FIN-002"):
                    self.findings.append(DeterministicFinding(
                        rule_id="AST-FIN-002",
                        rule_name="MissingIdempotencyGuard",
                        severity="HIGH",
                        category="IDEMPOTENCY",
                        line_start=line_start,
                        line_end=line_end,
                        col_offset=getattr(node, "col_offset", 0),
                        message=f"Endpoint '{route_path}' lacks Idempotency-Key guard. Retries may cause duplicate charge/settlement.",
                        suggested_fix="def " + getattr(node, "name", "handler") + "(..., idempotency_key: str = Header(..., alias='Idempotency-Key'))",
                        file_path=self.file_path
                    ))

    def visit_BinOp(self, node: ast.BinOp):
        """Rule AST-FIN-001: Detect float operations in financial context."""
        float_repr = self._extract_float_info(node.left) or self._extract_float_info(node.right)
        if float_repr is not None:
            line = getattr(node, "lineno", 1)
            in_fin = self.is_in_financial_context
            if not in_fin:
                for subnode in ast.walk(node):
                    if isinstance(subnode, ast.Name) and self._is_financial_name(subnode.id):
                        in_fin = True
                        break

            if in_fin and not self._is_suppressed(line, "AST-FIN-001"):
                op_symbol = self._get_op_symbol(node.op)
                self.findings.append(DeterministicFinding(
                    rule_id="AST-FIN-001",
                    rule_name="FloatInCurrencyArithmetic",
                    severity="CRITICAL",
                    category="LEDGER_INTEGRITY",
                    line_start=line,
                    line_end=getattr(node, "end_lineno", line),
                    col_offset=getattr(node, "col_offset", 0),
                    message=f"Detected float literal/cast ({float_repr}) in financial calculation ({op_symbol}). IEEE 754 precision loss will corrupt balances.",
                    suggested_fix=f"Use decimal.Decimal('{float_repr}') or integer cents (e.g. 100 cents = $1.00).",
                    file_path=self.file_path
                ))

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        float_repr = self._extract_float_info(node.value)
        if float_repr is not None:
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            if targets:
                self._check_float_assignment(node, float_repr, targets)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if node.value:
            float_repr = self._extract_float_info(node.value)
            if float_repr is not None:
                targets = [node.target] if isinstance(node.target, ast.Name) else []
                if targets:
                    self._check_float_assignment(node, float_repr, targets)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign):
        """Rule AST-FIN-001: Augmented assignment (e.g. balance += 10.5, fee *= 0.05)."""
        float_repr = self._extract_float_info(node.value)
        if float_repr is not None:
            targets = [node.target] if isinstance(node.target, ast.Name) else []
            if targets:
                self._check_float_assignment(node, float_repr, targets)
        self.generic_visit(node)

    def _check_float_assignment(self, node: ast.AST, float_repr: str, target_names: List[ast.Name]):
        line = getattr(node, "lineno", 1)
        var_names = [t.id for t in target_names]
        is_financial_var = any(self._is_financial_name(vn) for vn in var_names)
        if (self.is_in_financial_context or is_financial_var) and not self._is_suppressed(line, "AST-FIN-001"):
            targets_str = ", ".join(var_names) if var_names else "variable"
            self.findings.append(DeterministicFinding(
                rule_id="AST-FIN-001",
                rule_name="FloatInCurrencyArithmetic",
                severity="CRITICAL",
                category="LEDGER_INTEGRITY",
                line_start=line,
                line_end=getattr(node, "end_lineno", line),
                col_offset=getattr(node, "col_offset", 0),
                message=f"Detected float literal/cast ({float_repr}) assigned to financial variable '{targets_str}'. IEEE 754 precision loss will corrupt balances.",
                suggested_fix=f"Use decimal.Decimal('{float_repr}') or integer cents.",
                file_path=self.file_path
            ))


    # Fast leaf skips to eliminate recursion overhead on childless nodes
    def visit_Constant(self, node: ast.Constant): pass
    def visit_Name(self, node: ast.Name): pass
    def visit_Load(self, node: ast.Load): pass
    def visit_Store(self, node: ast.Store): pass
    def visit_Del(self, node: ast.Del): pass
    def visit_arg(self, node: ast.arg): pass
    def visit_arguments(self, node: ast.arguments): pass
    def visit_Pass(self, node: ast.Pass): pass
    def visit_Break(self, node: ast.Break): pass
    def visit_Continue(self, node: ast.Continue): pass

    def visit_With(self, node: ast.With):
        self._visit_with_block(node)

    def visit_AsyncWith(self, node: ast.AsyncWith):
        self._visit_with_block(node)

    def _visit_with_block(self, node: ast.AST):
        is_transaction = False
        items = getattr(node, "items", [])
        for item in items:
            ctx_expr = item.context_expr
            # Match db.begin(), session.begin(), transaction.atomic(), db.transaction()
            if isinstance(ctx_expr, ast.Call):
                func = ctx_expr.func
                attr = getattr(func, "attr", "")
                name = getattr(func, "id", "")
                if attr in TRANSACTION_CONTEXT_NAMES or name in TRANSACTION_CONTEXT_NAMES:
                    is_transaction = True
                    break

        if is_transaction:
            self.transaction_depth += 1

        self.generic_visit(node)

        if is_transaction:
            self.transaction_depth = max(0, self.transaction_depth - 1)

    def visit_Try(self, node: ast.Try):
        self.try_depth += 1
        self.generic_visit(node)
        self.try_depth = max(0, self.try_depth - 1)

    def visit_Call(self, node: ast.Call):
        line = getattr(node, "lineno", 1)

        # Rule AST-FIN-003: Network call inside database transaction lock
        if self.transaction_depth > 0 and self._is_network_call(node):
            if not self._is_suppressed(line, "AST-FIN-003"):
                call_name = self._get_call_name(node)
                self.findings.append(DeterministicFinding(
                    rule_id="AST-FIN-003",
                    rule_name="NetworkCallInsideTransactionBlock",
                    severity="CRITICAL",
                    category="TRANSACTION_ISOLATION",
                    line_start=line,
                    line_end=getattr(node, "end_lineno", line),
                    col_offset=getattr(node, "col_offset", 0),
                    message=f"External network call '{call_name}' executed inside database transaction lock. Will cause lock contention and pool exhaustion.",
                    suggested_fix="Perform external network requests outside 'with db.begin():' block; record state transition after response.",
                    file_path=self.file_path
                ))

        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr):
        """Rule AST-FIN-004: Unchecked return on balance debit statement."""
        line = getattr(node, "lineno", 1)
        val = node.value
        # Support both synchronous calls account.debit() and async await account.debit()
        if isinstance(val, ast.Await):
            val = val.value

        if isinstance(val, ast.Call):
            call_name = self._get_call_name(val)
            base_func = call_name.split(".")[-1].lower()

            if base_func in DEBIT_FUNCTION_PATTERNS and self.try_depth == 0:
                if not self._is_suppressed(line, "AST-FIN-004"):
                    self.findings.append(DeterministicFinding(
                        rule_id="AST-FIN-004",
                        rule_name="UncheckedDebitReturn",
                        severity="CRITICAL",
                        category="LEDGER_INTEGRITY",
                        line_start=line,
                        line_end=getattr(node, "end_lineno", line),
                        col_offset=getattr(node, "col_offset", 0),
                        message=f"Call to '{call_name}' discards return value without status check or exception handling. Negative balance overflow risk.",
                        suggested_fix=f"if not {call_name}(...): raise InsufficientFundsError()",
                        file_path=self.file_path
                    ))

        self.generic_visit(node)

    def _is_network_call(self, node: ast.Call) -> bool:
        func = node.func
        if isinstance(func, ast.Attribute):
            attr = func.attr
            val = func.value
            val_id = getattr(val, "id", "")
            val_attr = getattr(val, "attr", "")
            
            # e.g. requests.post, httpx.get, client.post
            if val_id in NETWORK_CALL_MODULES or "client" in val_id.lower() or "session" in val_id.lower():
                if attr in NETWORK_CALL_METHODS:
                    return True
            # e.g. urllib.request.urlopen
            if val_attr == "request" and attr in NETWORK_CALL_METHODS:
                return True
        elif isinstance(func, ast.Name):
            # Bare calls like urlopen(...) or post(...)
            if func.id == "urlopen" or (func.id in NETWORK_CALL_METHODS and self.current_function_name != func.id):
                return True
        return False


    def _get_call_name(self, node: ast.Call) -> str:
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        elif isinstance(func, ast.Attribute):
            val_name = getattr(func.value, "id", "") or getattr(func.value, "attr", "obj")
            return f"{val_name}.{func.attr}"
        return "call"

    def _get_op_symbol(self, op: ast.operator) -> str:
        if isinstance(op, ast.Add): return "+"
        if isinstance(op, ast.Sub): return "-"
        if isinstance(op, ast.Mult): return "*"
        if isinstance(op, ast.Div): return "/"
        if isinstance(op, ast.FloorDiv): return "//"
        if isinstance(op, ast.Mod): return "%"
        if isinstance(op, ast.Pow): return "**"
        return "arithmetic"
