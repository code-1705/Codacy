"""
FinGuard CLI: Git & Repository Utilities
Safely extracts diffs from local git repository and manages pre-commit hooks.
"""
import os
import subprocess
import stat
from typing import Optional


def get_git_diff(staged: bool = False, file_path: Optional[str] = None) -> str:
    """
    Extracts unified git diff from the local workstation repository.
    """
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")
    else:
        cmd.append("HEAD")

    if file_path:
        cmd.extend(["--", file_path])

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False
        )
        diff_output = proc.stdout.strip()

        # If diff is empty and a file_path was requested, fall back to reading file as synthetic diff
        if not diff_output and file_path and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            lines = [f"+{line}" for line in content.splitlines()]
            return f"--- a/{file_path}\n+++ b/{file_path}\n@@ -0,0 +1,{len(lines)} @@\n" + "\n".join(lines)

        return diff_output
    except Exception:
        return ""


def split_diff_by_files(diff_text: str) -> list:
    """
    Splits a multi-file unified git diff into individual (file_path, diff_content) tuples.
    Enables isolated per-file review without one file's quarantine halting the whole diff.
    """
    if not diff_text or not diff_text.strip():
        return []

    file_diffs = []
    current_file = ""
    current_lines = []

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current_lines:
                file_diffs.append((current_file or "git-diff", "\n".join(current_lines)))
                current_lines = []
            parts = line.split(" ")
            if len(parts) >= 4 and parts[3].startswith("b/"):
                current_file = parts[3][2:]
            else:
                current_file = "git-diff"
        current_lines.append(line)

    if current_lines:
        file_diffs.append((current_file or "git-diff", "\n".join(current_lines)))

    return file_diffs


def get_git_repo_metadata() -> dict:
    """Extracts current git commit SHA, author, and branch name."""
    meta = {
        "repo": "org/local-repo",
        "commit_sha": "0000000000000000000000000000000000000000",
        "author": "developer@fintech.corp"
    }
    try:
        sha_proc = subprocess.run(["git", "rev-parse", "HEAD"], stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False)
        if sha_proc.returncode == 0 and sha_proc.stdout.strip():
            meta["commit_sha"] = sha_proc.stdout.strip()

        author_proc = subprocess.run(["git", "config", "user.email"], stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False)
        if author_proc.returncode == 0 and author_proc.stdout.strip():
            meta["author"] = author_proc.stdout.strip()

        repo_proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], stdout=subprocess.PIPE, text=True, check=False)
        if repo_proc.returncode == 0 and repo_proc.stdout.strip():
            meta["repo"] = os.path.basename(repo_proc.stdout.strip())
    except Exception:
        pass

    return meta


def install_pre_commit_hook(repo_root: str = ".") -> str:
    """Installs FinGuard as a pre-commit git hook in .git/hooks/pre-commit."""
    hooks_dir = os.path.join(repo_root, ".git", "hooks")
    if not os.path.exists(hooks_dir):
        os.makedirs(hooks_dir, exist_ok=True)

    hook_path = os.path.join(hooks_dir, "pre-commit")
    hook_content = """#!/bin/sh
# FinGuard Pre-Commit Verification Hook
# Automatically blocks commits containing CRITICAL FinTech bugs or secret leaks.

finguard review --staged --severity critical
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo ""
  echo "🛡️ FinGuard Gatekeeper: Commit aborted due to CRITICAL financial regressions."
  echo "Run 'finguard review --staged' to view detailed analysis and verified patches."
  exit 1
fi
exit 0
"""
    with open(hook_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(hook_content)

    # Ensure executable permissions on Unix/macOS/Linux
    try:
        st = os.stat(hook_path)
        os.chmod(hook_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

    return hook_path


def uninstall_pre_commit_hook(repo_root: str = ".") -> bool:
    """Removes the FinGuard pre-commit git hook."""
    hook_path = os.path.join(repo_root, ".git", "hooks", "pre-commit")
    if os.path.exists(hook_path):
        os.remove(hook_path)
        return True
    return False
