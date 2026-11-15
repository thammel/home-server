#!/usr/bin/env bash
# Stop: run pytest when Python files changed. On failure, exit 2 so Claude keeps working.
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 0
input=$(cat)
# Avoid loops: if this Stop was already triggered by a hook, let Claude stop.
echo "$input" | grep -q '"stop_hook_active": *true' && exit 0
[ -x .venv/bin/pytest ] || exit 0
changed=$( { git diff --name-only HEAD; git ls-files --others --exclude-standard; } 2>/dev/null | grep -E '^(app|tests)/.*\.py$')
[ -z "$changed" ] && exit 0
out=$(.venv/bin/pytest -q -x 2>&1)
if [ $? -ne 0 ]; then
  echo "Tests failing after your changes:" >&2
  echo "$out" | tail -40 >&2
  exit 2
fi
exit 0
