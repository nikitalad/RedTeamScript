#!/usr/bin/env bash
set -euo pipefail
target="demo-project/README.md"
[ -f "${target}.bak" ] && mv "${target}.bak" "$target"
