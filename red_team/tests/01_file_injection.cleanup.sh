#!/usr/bin/env bash
set -euo pipefail
target="demo-project/storage.py"
[ -f "${target}.bak" ] && mv "${target}.bak" "$target"
