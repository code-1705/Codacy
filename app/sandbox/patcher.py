"""
FinGuard Tier 4: In-Memory Unified Diff Patcher
Applies unified git diff patches to source code strings without external patch binaries.
"""
import re
from typing import List, Tuple


class PatchApplicationError(Exception):
    """Raised when a unified diff fails to cleanly apply."""
    pass


def apply_patch(original_code: str, patch_diff: str) -> str:
    """
    Applies a unified git diff to the given original code string.
    Returns the resulting modified source code.
    Raises PatchApplicationError if hunks cannot be aligned.
    """
    if not patch_diff or not patch_diff.strip():
        return original_code

    diff_lines = patch_diff.strip().splitlines()
    orig_lines = original_code.splitlines()

    # Locate hunk headers: @@ -start_old[,len_old] +start_new[,len_new] @@
    hunk_regex = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

    hunks = []
    current_hunk = None

    for line in diff_lines:
        match = hunk_regex.match(line)
        if match:
            if current_hunk:
                hunks.append(current_hunk)
            start_old = int(match.group(1))
            current_hunk = {
                "start_old": start_old,
                "lines": []
            }
        elif current_hunk is not None:
            if line.startswith(("+", "-", " ")):
                current_hunk["lines"].append(line)

    if current_hunk:
        hunks.append(current_hunk)

    if not hunks:
        # If no hunk headers found, try direct replacement if patch specifies single replacement
        return original_code

    # Apply hunks from bottom to top so line number shifts don't affect subsequent hunks
    hunks.sort(key=lambda h: h["start_old"], reverse=True)
    result_lines = list(orig_lines)

    for hunk in hunks:
        start_idx = max(0, hunk["start_old"] - 1)
        hunk_lines = hunk["lines"]

        # Extract expected old lines from hunk (context + deletions)
        expected_old = [l[1:] for l in hunk_lines if l.startswith((" ", "-"))]
        replacement_new = [l[1:] for l in hunk_lines if l.startswith((" ", "+"))]

        # Try to find exact match around start_idx
        match_found = False
        target_idx = start_idx

        # Check at start_idx first
        if target_idx + len(expected_old) <= len(result_lines):
            if result_lines[target_idx:target_idx + len(expected_old)] == expected_old:
                match_found = True

        # Search window +- 10 lines if offset shifted
        if not match_found:
            for offset in range(1, 15):
                # Try before
                pos = start_idx - offset
                if 0 <= pos and pos + len(expected_old) <= len(result_lines):
                    if result_lines[pos:pos + len(expected_old)] == expected_old:
                        target_idx = pos
                        match_found = True
                        break
                # Try after
                pos = start_idx + offset
                if pos + len(expected_old) <= len(result_lines):
                    if result_lines[pos:pos + len(expected_old)] == expected_old:
                        target_idx = pos
                        match_found = True
                        break

        if match_found:
            # Replace old lines with new lines
            result_lines[target_idx:target_idx + len(expected_old)] = replacement_new
        else:
            # Fallback: substring replacement for simple one-line changes
            old_str = "\n".join(expected_old)
            new_str = "\n".join(replacement_new)
            cur_text = "\n".join(result_lines)
            if old_str in cur_text:
                cur_text = cur_text.replace(old_str, new_str, 1)
                result_lines = cur_text.splitlines()
            else:
                raise PatchApplicationError(f"Hunk starting at line {hunk['start_old']} could not be matched.")

    return "\n".join(result_lines) + ("\n" if original_code.endswith("\n") else "")
