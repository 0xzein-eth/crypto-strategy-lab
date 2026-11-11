#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  adaptive_state|adaptive_history) target="$1" ;;
  *) echo "Invalid isolated adaptive persistence target"; exit 1 ;;
esac
test -z "$(git status --porcelain data/ v2_state/ equity_state/ stock_lab_state/ research_cache/ research_results/ v2_history/)"
git diff --check
if ! test -d "$target"; then exit 0; fi
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A -- "$target/"
if git diff --cached --quiet; then exit 0; fi
git commit -m "research(adaptive): isolated authentic ${target} evidence [skip ci]"
for attempt in 1 2 3; do
  if git push origin HEAD:main; then exit 0; fi
  git fetch origin main
  if ! git rebase origin/main; then
    git rebase --abort || true
    echo 'PERSISTENCE_FAILURE: refused conflicting evidence, no force push'
    exit 1
  fi
  if test "$target" = adaptive_state; then
    python -m adaptive_lab.engine --verify-only
  fi
done
echo 'PERSISTENCE_FAILURE: new evidence remains available in run artifact'
exit 1
