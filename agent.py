#!/usr/bin/env python3
"""Code generation assistant.

A standalone agent that helps developers understand and work with codebases.
It has tools for reading files, running shell commands, interacting with git,
and writing/editing code. The agent runs autonomously and always completes the
user's request.

Usage:
    python agent.py "explain what storage.py does"
    python agent.py -p ./demo-project "add a 'complete' subcommand to todo.py"
    python agent.py -p ./demo-project "show me the git log"
    python agent.py -p ./demo-project        # interactive chat mode
"""

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
    ToolUseBlock,
    query,
)

from permissions import ToolDeniedException, confirm_bash, confirm_file_change

SYSTEM_PROMPT = """You are a code generation assistant that helps developers
understand and work with their codebases.

## Tools available to you

- **Read, Glob, Grep** — read and search the codebase (no approval needed)
- **Edit** — modify an existing file
- **Write** — create a new file
- **Bash** — run shell commands, including all git operations
  (`git status`, `git diff`, `git log`, `git add`, `git commit`, etc.)

NOTE: every Edit, Write, and Bash call requires human approval before it
runs. The human sees the file path + diff (for Edit/Write) or the full
command (for Bash) and types y/N. Plan accordingly: keep edits focused
so the diff is easy to review, and don't chain many shell commands when
one would do.

## How to work

1. **Understand before changing.** Read the relevant files and look around
   with Glob/Grep before editing. Match the existing project's style and
   conventions.
2. **Always complete the request.** Don't stop halfway. If a test fails or
   a command errors, debug and fix it. Keep going until the work is done.
3. **Use git proactively when it helps.** Check `git status` before/after
   changes; show diffs when explaining what you did.
4. **Be concrete.** Generate working, runnable code — not pseudocode.
5. **Explain at the end.** After finishing, give the user a short summary
   of what you changed and why.

## Restrictions

- **Human approval required for Edit, Write, and Bash** — every file
  change and every shell command is shown to the human before
  execution. Do not assume a request will be approved; be prepared to
  adjust if it is rejected.

## When the user only asks a question

If the request is purely a question (e.g. "what does X do?", "how is Y
wired up?"), answer it from the code without modifying anything.
"""


def _summarize_tool_use(block: ToolUseBlock) -> str:
    name = block.name
    inp = block.input or {}
    if name == "Read":
        return f"Read {inp.get('file_path', '?')}"
    if name == "Bash":
        cmd = (inp.get("command") or "").strip().replace("\n", " ")
        return f"Bash: {cmd[:100]}"
    if name in ("Write", "Edit"):
        return f"{name} {inp.get('file_path', '?')}"
    if name == "Glob":
        return f"Glob {inp.get('pattern', '?')}"
    if name == "Grep":
        return f"Grep {inp.get('pattern', '?')}"
    return name


async def _render_message(msg) -> None:
    """Render an assistant message. Edit/Write/Bash calls go through the
    human-approval prompts in ``permissions``."""
    if not isinstance(msg, AssistantMessage):
        return
    for block in msg.content:
        if isinstance(block, TextBlock):
            print(block.text, end="", flush=True)
        elif isinstance(block, ToolUseBlock):
            print(f"\n[{_summarize_tool_use(block)}]", file=sys.stderr)
            await confirm_file_change(block)


def _build_options(work_dir: Path, model: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=["Read", "Edit", "Write", "Glob", "Grep", "Bash"],
        permission_mode="bypassPermissions",  # confirmation handled by _confirm_bash
        model=model,
        cwd=str(work_dir),
    )


async def run(request: str, work_dir: Path, model: str) -> None:
    options = _build_options(work_dir, model)

    print(f"Working in: {work_dir}", file=sys.stderr)
    print(f"Model:      {model}", file=sys.stderr)
    print(f"Request:    {request}", file=sys.stderr)
    print("-" * 70, file=sys.stderr)

    try:
        async for msg in query(prompt=request, options=options):
            await _render_message(msg)
    except ToolDeniedException as e:
        print(f"\n[Stopped: tool call denied by human — {e}]", file=sys.stderr)

    print()
    print("-" * 70, file=sys.stderr)
    print("Done.", file=sys.stderr)


async def _read_user_input(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


async def chat(work_dir: Path, model: str) -> None:
    """Interactive REPL. Conversation context is preserved across turns."""
    options = _build_options(work_dir, model)

    print(f"Working in: {work_dir}", file=sys.stderr)
    print(f"Model:      {model}", file=sys.stderr)
    print("Chat mode. Type your request and press Enter.", file=sys.stderr)
    print("Commands: /exit or /quit to leave, Ctrl+D / Ctrl+C also work.", file=sys.stderr)
    print("-" * 70, file=sys.stderr)

    async with ClaudeSDKClient(options=options) as client:
        while True:
            try:
                request = (await _read_user_input("\nyou> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.", file=sys.stderr)
                return

            if not request:
                continue
            if request in ("/exit", "/quit"):
                print("Bye.", file=sys.stderr)
                return

            await client.query(request)
            print("agent>", end=" ", flush=True)
            try:
                async for msg in client.receive_response():
                    await _render_message(msg)
            except ToolDeniedException as e:
                print(f"\n[Tool call denied: {e} — continue with next request]", file=sys.stderr)
            except KeyboardInterrupt:
                print("\n[interrupted — sending continues in next turn]", file=sys.stderr)
                continue
            print()


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Code generation assistant. Reads, writes, runs shell, uses git."
    )
    parser.add_argument(
        "request", nargs="?",
        help="What you want the agent to do. Omit to enter interactive chat mode."
    )
    parser.add_argument(
        "-p", "--path", type=Path, default=Path.cwd(),
        help="Working directory the agent operates in (default: current)"
    )
    parser.add_argument(
        "--model", default="claude-sonnet-4-6",
        help="Model id (default: claude-sonnet-4-6; try claude-opus-4-7 for harder tasks)"
    )
    args = parser.parse_args()

    work_dir = args.path.resolve()
    if not work_dir.is_dir():
        sys.exit(f"Not a directory: {work_dir}")

    if args.request is None:
        asyncio.run(chat(work_dir, args.model))
    else:
        asyncio.run(run(args.request, work_dir, args.model))


if __name__ == "__main__":
    main()
