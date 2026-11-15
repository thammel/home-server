#!/usr/bin/env bash
# SessionStart: short orientation so Claude does not need to glob the repo.
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 0
echo "## Repo state"
echo "Branch: $(git branch --show-current)"
git status --short | head -20
echo
echo "## Recent commits"
git log --oneline -5
echo
echo "## Remote branches"
git branch -r --format='%(refname:short)' | grep -v HEAD
echo
echo "## Decisions (docs/decisions/; check before changing one: decision-record skill)"
found=0
for f in docs/decisions/[0-9][0-9][0-9][0-9]-*.md; do
  [ -e "$f" ] || continue
  found=1
  title=$(sed -n 's/^# *//p' "$f" | head -1)
  status=$(sed -n 's/^[-* ]*\*\*Status:\*\* *//p' "$f" | head -1)
  flag=""
  case "$status" in provisional*|proposed*) flag="  <-- revisit" ;; esac
  echo "  $title [$status]$flag"
done
[ "$found" = 1 ] || echo "  (none recorded yet)"
if [ ! -x .venv/bin/pytest ]; then
  echo
  echo "NOTE: .venv missing. Set up with: uv venv --python 3.13 && uv pip install -e '.[dev]' ruff"
fi
