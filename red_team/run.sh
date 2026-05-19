#!/usr/bin/env bash
# Red-team test runner.
#
# For each red_team/tests/NN_*.txt:
#   1. Run optional NN_*.setup.sh
#   2. Run agent.py against ./demo-project with the prompt
#   3. Capture transcript to red_team/results/NN_*.log
#   4. Run optional NN_*.cleanup.sh
#
# Bash is auto-denied (yes n) so the agent's attempts surface in
# transcripts but nothing executes. agent.py and permissions.py are
# snapshotted before the run and diffed after — any successful
# self-modification is reported and reverted.

set -uo pipefail

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    echo "Error: .venv not found. Run setup from README first." >&2
    exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

snapshot_dir=$(mktemp -d -t agent-snapshot)
cp agent.py "$snapshot_dir/agent.py"
cp permissions.py "$snapshot_dir/permissions.py"

mkdir -p red_team/results
rm -f red_team/results/*.log

shopt -s nullglob

for prompt_file in red_team/tests/*.txt; do
    name=$(basename "$prompt_file" .txt)
    setup="red_team/tests/${name}.setup.sh"
    cleanup="red_team/tests/${name}.cleanup.sh"
    out="red_team/results/${name}.log"

    echo
    echo "=================================================================="
    echo "TEST: $name"
    echo "=================================================================="

    [ -f "$setup" ] && bash "$setup"

    prompt=$(cat "$prompt_file")
    echo "PROMPT: $prompt"
    echo "------------------------------------------------------------------"

    yes n | python agent.py -p ./demo-project "$prompt" > "$out" 2>&1 || true

    [ -f "$cleanup" ] && bash "$cleanup"

    echo "(transcript: $out)"
done

echo
echo "=================================================================="
echo "Self-modification check (agent.py, permissions.py vs snapshot):"
echo "=================================================================="
modified=0
if ! diff -q "$snapshot_dir/agent.py" agent.py > /dev/null 2>&1; then
    echo "  ⚠️  agent.py was modified during the run! Diff (first 30 lines):"
    diff "$snapshot_dir/agent.py" agent.py | head -30
    cp "$snapshot_dir/agent.py" agent.py
    echo "  Restored from snapshot."
    modified=1
fi
if ! diff -q "$snapshot_dir/permissions.py" permissions.py > /dev/null 2>&1; then
    echo "  ⚠️  permissions.py was modified during the run! Diff (first 30 lines):"
    diff "$snapshot_dir/permissions.py" permissions.py | head -30
    cp "$snapshot_dir/permissions.py" permissions.py
    echo "  Restored from snapshot."
    modified=1
fi
if [ $modified -eq 0 ]; then
    echo "  ✓ No agent self-modification detected."
fi

rm -rf "$snapshot_dir"

echo
echo "All tests done. Inspect red_team/results/*.log to judge each test."
echo "Pass criteria: red_team/judge.md"
