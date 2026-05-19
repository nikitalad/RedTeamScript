#!/usr/bin/env bash
set -euo pipefail
target="demo-project/.github/workflows/ci.yml"
[ -f "${target}.bak" ] && mv "${target}.bak" "$target"
