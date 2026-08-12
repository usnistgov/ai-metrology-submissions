#!/usr/bin/env bash
#
# Which open pull requests are worth reviewing?  One line each.
#
#     validation/check-prs.sh
#     validation/check-prs.sh --verbose     # show why the failures fail
#
# Runs check-pr.sh over every open pull request and prints a ✅/❌ summary. Read-only:
# publishes nothing, changes nothing, touches no check run.
#
# Requires the same as check-pr.sh, which it calls once per pull request:
#   pip:      PyYAML~=6.0, check-jsonschema~=0.38
#   commands: git, python3, and either `gh` (authenticated) or `curl` + GITHUB_TOKEN
#
#     pip install "PyYAML~=6.0" "check-jsonschema~=0.38"

set -euo pipefail

REPO="${REPO:-usnistgov/ai-metrology-submissions}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERBOSE=0

# The header comment above is the help text, printed from the file itself.
usage() { awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; }

case "${1:-}" in
  "") ;;
  -h|--help) usage; exit 2 ;;
  -v|--verbose) VERBOSE=1 ;;
  # Without this arm, `check-prs.sh 42` silently swept every open pull request — the
  # obvious slip, given check-pr.sh takes a number and sits beside it in the README.
  *) echo "unknown argument: $1 — did you mean check-pr.sh $1 ?" >&2; exit 2 ;;
esac

if command -v gh >/dev/null 2>&1; then
  NUMBERS="$(gh pr list --repo "$REPO" --state open --limit 100 --json number --jq '.[].number')"
else
  NUMBERS="$(curl -sSf ${GITHUB_TOKEN:+-H "Authorization: token $GITHUB_TOKEN"} \
    "https://api.github.com/repos/$REPO/pulls?state=open&per_page=100" \
    | python3 -c 'import json,sys; [print(p["number"]) for p in json.load(sys.stdin)]')"
fi

if [[ -z "$NUMBERS" ]]; then
  echo "No open pull requests."
  exit 0
fi

echo "Checking $(wc -w <<<"$NUMBERS" | tr -d ' ') open pull request(s) in $REPO"
echo

TOTAL=0
FAILED=0
UNKNOWN=0
for n in $NUMBERS; do
  TOTAL=$((TOTAL + 1))
  OUTPUT="$("$HERE/check-pr.sh" "$n" 2>&1)" && RESULT=0 || RESULT=$?
  # Strip control characters: this line puts attacker bytes immediately after the
  # verdict icon, so ESC here can repaint the rows above it in the summary.
  TITLE="$(sed -n '1p' <<<"$OUTPUT" | LC_ALL=C tr -d '\000-\037\177')"
  case $RESULT in
    0) printf '✅  %s\n' "$TITLE" ;;
    1) printf '❌  %s\n' "$TITLE"; FAILED=$((FAILED + 1)) ;;
    # Anything else means the check could not run — a network blip, a missing tool.
    # Reporting that as ❌ would libel a submission that may be perfectly fine.
    *) printf '⚠️   PR #%s — could not check\n' "$n"; UNKNOWN=$((UNKNOWN + 1)) ;;
  esac
  if [[ $VERBOSE -eq 1 && $RESULT -ne 0 ]]; then
    # Only drop line 1 when it is the title line. An exit-4 run never printed one, so
    # blanket-dropping it deleted the single line saying why it could not be checked.
    if [[ $RESULT -eq 1 ]]; then sed '1d' <<<"$OUTPUT"; else printf '%s\n' "$OUTPUT"; fi \
      | sed 's/^/      /'
    echo
  fi
done

echo
if [[ $FAILED -eq 0 && $UNKNOWN -eq 0 ]]; then
  echo "All $TOTAL pass validation."
else
  [[ $FAILED -gt 0 ]] && echo "$FAILED of $TOTAL fail validation."
  [[ $UNKNOWN -gt 0 ]] && echo "$UNKNOWN of $TOTAL could not be checked — re-run those."
  [[ $VERBOSE -eq 0 ]] && echo "Re-run with --verbose, or check-pr.sh <number>, for detail."
fi
exit 0
