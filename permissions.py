"""Human-in-the-loop permission handling for the code-generation agent.

The agent runs with ``permission_mode="bypassPermissions"`` so the Claude
Agent SDK does not prompt before tool calls. We layer our own approval
step on top: every **Edit**, **Write**, and **Bash** call is shown to
the human and only proceeds if they type 'y'/'yes'. Read/Glob/Grep pass
through without prompting (they don't change anything).

Public API
----------
- ``ToolDeniedException``       — raised when the human denies a call.
- ``confirm_bash(block)``       — gate Bash calls.
- ``confirm_file_change(block)`` — gate Edit/Write calls.
"""

import asyncio
import sys

from claude_agent_sdk import ToolUseBlock


class ToolDeniedException(Exception):
    """Raised when the human rejects a tool call (Bash, Edit, or Write)."""


def _truncate(text: str, limit: int) -> str:
    """Trim ``text`` to ``limit`` chars with a marker if anything was cut."""
    text = text.replace("\r\n", "\n")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text) - limit} more chars]"


async def _prompt(question: str) -> bool:
    """Ask the human a yes/no question. Returns True only on 'y' or 'yes'."""
    answer = await asyncio.to_thread(input, question)
    approved = answer.strip().lower() in ("y", "yes")
    if approved:
        print("  ✓ Approved.\n", file=sys.stderr)
    else:
        print("  ✗ Denied — agent will be told the call was not made.\n", file=sys.stderr)
    return approved


async def confirm_bash(block: ToolUseBlock) -> None:
    """Ask the human before a Bash call. Raise ``ToolDeniedException`` on denial.

    Returns silently for non-Bash blocks and approved Bash calls.
    """
    if block.name != "Bash":
        return
    cmd = (block.input or {}).get("command", "").strip()
    print(f"\n{'─' * 60}", file=sys.stderr)
    print(f"  ⚠️  Agent wants to run a Bash command:", file=sys.stderr)
    print(f"  $ {cmd}", file=sys.stderr)
    print(f"{'─' * 60}", file=sys.stderr)
    if not await _prompt("  Approve? [y/N]: "):
        raise ToolDeniedException(f"Bash: {cmd}")


async def confirm_file_change(block: ToolUseBlock) -> None:
    """Ask the human before an Edit or Write call.

    Shows the file path and a preview of the change (the old/new strings
    for Edit, the first 30 lines of content for Write). Raises
    ``ToolDeniedException`` on denial. Returns silently for non-Edit/Write
    blocks and approved calls.
    """
    if block.name not in ("Edit", "Write"):
        return
    inp = block.input or {}
    file_path = inp.get("file_path", "<unknown>")

    print(f"\n{'─' * 60}", file=sys.stderr)
    print(f"  ⚠️  Agent wants to {block.name} a file:", file=sys.stderr)
    print(f"  Path: {file_path}", file=sys.stderr)

    if block.name == "Edit":
        old = inp.get("old_string", "")
        new = inp.get("new_string", "")
        if inp.get("replace_all"):
            print(f"  Mode: replace_all", file=sys.stderr)
        print(f"  - Remove:", file=sys.stderr)
        for line in (_truncate(old, 400).splitlines() or [""]):
            print(f"      {line}", file=sys.stderr)
        print(f"  + Insert:", file=sys.stderr)
        for line in (_truncate(new, 400).splitlines() or [""]):
            print(f"      {line}", file=sys.stderr)
    else:  # Write
        content = inp.get("content", "")
        all_lines = content.splitlines()
        preview = all_lines[:30]
        print(f"  Content ({len(all_lines)} lines, showing first {len(preview)}):", file=sys.stderr)
        for line in preview:
            print(f"    | {line}", file=sys.stderr)
        if len(all_lines) > len(preview):
            print(f"    | ... [{len(all_lines) - len(preview)} more lines]", file=sys.stderr)

    print(f"{'─' * 60}", file=sys.stderr)
    if not await _prompt("  Approve? [y/N]: "):
        raise ToolDeniedException(f"{block.name}: {file_path}")
