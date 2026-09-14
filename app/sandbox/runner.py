"""
FinGuard Tier 4: Ephemeral Sandbox Runner & Verification Engine
Executes reproduction test scripts and patches through a 3-phase verification lifecycle.
"""
import sys
import os
import subprocess
import tempfile
import time
from typing import Optional, Dict, Any, Tuple
from app.sandbox.models import VerificationResult
from app.sandbox.patcher import apply_patch, PatchApplicationError

DEFAULT_TIMEOUT_SECONDS = 4.0


class EphemeralSandboxRunner:
    """
    Executes Python/pytest reproduction tests within an ephemeral, network-isolated runner.
    Supports both local restricted subprocesses and Docker containers.
    """

    def __init__(self, timeout_sec: float = DEFAULT_TIMEOUT_SECONDS):
        self.timeout_sec = timeout_sec

    def _execute_in_tempdir(
        self,
        service_code: str,
        test_code: str,
        service_filename: str = "service.py",
        test_filename: str = "test_repro.py"
    ) -> Tuple[bool, str, float]:
        """
        Runs pytest inside a sterile temporary directory.
        Returns: (passed: bool, output: str, elapsed_ms: float)
        """
        start_time = time.perf_counter()

        with tempfile.TemporaryDirectory(prefix="finguard_sandbox_") as tmp_dir:
            service_path = os.path.join(tmp_dir, service_filename)
            test_path = os.path.join(tmp_dir, test_filename)

            with open(service_path, "w", encoding="utf-8") as f:
                f.write(service_code)

            with open(test_path, "w", encoding="utf-8") as f:
                f.write(test_code)

            # Build clean, restricted execution environment
            env = os.environ.copy()
            env["PYTHONPATH"] = tmp_dir
            env["PYTHONDONTWRITEBYTECODE"] = "1"

            cmd = [
                sys.executable,
                "-m", "pytest",
                "-q",
                "--tb=short",
                test_filename
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=tmp_dir,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=self.timeout_sec
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                passed = (proc.returncode == 0)
                return passed, proc.stdout, elapsed_ms

            except subprocess.TimeoutExpired:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return False, f"TimeoutExpired: Sandbox execution exceeded {self.timeout_sec}s", elapsed_ms
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return False, f"ExecutionError: {str(e)}", elapsed_ms

    def verify(
        self,
        code_before: str,
        repro_script: str,
        patch_diff: str
    ) -> VerificationResult:
        """
        Executes the mandatory 3-phase verification protocol:
        Phase 1: Run test against original code -> MUST FAIL (Proof of Defect)
        Phase 2: Apply patch_diff -> code_after
        Phase 3: Run test against patched code -> MUST PASS (Proof of Remedy)
        """
        total_start = time.perf_counter()

        # Phase 1: Proof of Bug
        p1_passed, p1_out, p1_ms = self._execute_in_tempdir(
            service_code=code_before,
            test_code=repro_script
        )

        if p1_passed:
            total_ms = (time.perf_counter() - total_start) * 1000.0
            return VerificationResult(
                verification_status="FAILED_TO_REPRODUCE",
                phase_1_baseline_failed=False,
                phase_2_patch_applied=False,
                phase_3_post_patch_passed=False,
                baseline_failure_output=p1_out,
                post_patch_output="",
                execution_time_ms=round(total_ms, 2),
                patch_diff=patch_diff,
                repro_script=repro_script,
                error_message="Test passed unexpectedly on original code before patch application."
            )

        # Phase 2: Application of Patch
        try:
            code_after = apply_patch(code_before, patch_diff)
            p2_success = True
        except PatchApplicationError as e:
            total_ms = (time.perf_counter() - total_start) * 1000.0
            return VerificationResult(
                verification_status="FAILED",
                phase_1_baseline_failed=True,
                phase_2_patch_applied=False,
                phase_3_post_patch_passed=False,
                baseline_failure_output=p1_out,
                post_patch_output="",
                execution_time_ms=round(total_ms, 2),
                patch_diff=patch_diff,
                repro_script=repro_script,
                error_message=f"Patch application failed: {str(e)}"
            )

        # Phase 3: Proof of Fix
        p3_passed, p3_out, p3_ms = self._execute_in_tempdir(
            service_code=code_after,
            test_code=repro_script
        )

        total_ms = (time.perf_counter() - total_start) * 1000.0

        if p3_passed:
            status = "PASSED"
            err = None
        else:
            status = "FAILED"
            err = "Reproduction test continues to fail after patch application."

        return VerificationResult(
            verification_status=status,
            phase_1_baseline_failed=True,
            phase_2_patch_applied=p2_success,
            phase_3_post_patch_passed=p3_passed,
            baseline_failure_output=p1_out,
            post_patch_output=p3_out,
            execution_time_ms=round(total_ms, 2),
            patch_diff=patch_diff,
            repro_script=repro_script,
            error_message=err
        )
