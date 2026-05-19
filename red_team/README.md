# Red-team payloads for the code-generation agent

A small suite that exercises the agent's resistance to prompt injection,
bash-approval evasion, path traversal, persona swaps, and tool-name
confusion.

## How to run

```bash
cd /Users/nikita/Downloads/code-improvement-agent
bash red_team/run.sh
```

The runner:

1. Snapshots `agent.py` and `permissions.py` so any successful
   self-modification can be detected (and reverted) at the end.
2. For each `red_team/tests/NN_*.txt`, runs the corresponding
   `*.setup.sh` (if any), invokes `python agent.py -p ./demo-project
   "<prompt>"`, captures the transcript to `red_team/results/`, then
   runs `*.cleanup.sh` (if any).
3. Bash calls are auto-denied (`yes n |`) so the agent's *attempts* are
   visible in the transcripts but nothing actually executes. Read,
   Edit, Glob, Grep still run freely — those are the interesting paths.
4. Diffs the snapshot at the end; if `agent.py` or `permissions.py`
   changed, the test surfaces it loudly and restores the snapshot.

## Reviewing results

Open `red_team/results/<test>.log`, then check `red_team/judge.md` for
the per-test PASS criteria. Most pass/fail calls are human judgment —
the LLM's wording varies between runs, and what matters is whether it
*tried* to do the malicious thing or refused.

## Switching to auto-approve

To see what the agent would do with a careless human (auto-approving
every Bash), edit `run.sh` and change `yes n |` to `yes y |`. Note: it
will then actually execute commands. Only do this if you understand
what each prompt asks the agent to attempt.
