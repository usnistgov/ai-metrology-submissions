#!/usr/bin/env bash
#
# Does this pull request pass submission validation?  A reviewer's sanity check.
#
#     validation/check-pr.sh 42
#
# Prints ✅ or ❌ and, when it fails, what is wrong. Read-only in every sense: it
# publishes nothing, changes no pull request, touches no check run, and leaves your
# working tree and current branch exactly as they were. It does not care whether the
# pull request already has a check — it just tells you whether the submission is
# well-formed enough to be worth reading.
#
# Exit status:  0 = passes    1 = fails validation    4 = could not check (see stderr)
#
# Requires
#   pip:      PyYAML~=6.0            (for validate_submission.py, run as python3)
#             check-jsonschema~=0.38 (run as a command, so it must be on PATH)
#   commands: git, python3, and either `gh` (authenticated) or `curl` + GITHUB_TOKEN
#
#     pip install "PyYAML~=6.0" "check-jsonschema~=0.38"

set -uo pipefail

REPO="${REPO:-usnistgov/ai-metrology-submissions}"
NUMBER="${1:-}"

# The header comment above is the help text — printed from the file itself so the two
# cannot drift apart.
usage() { awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; }

if [[ -z "$NUMBER" || "$NUMBER" == "-h" || "$NUMBER" == "--help" ]]; then
  usage
  exit 2
fi

# A problem reaching GitHub is not a verdict on the submission. Keeping it separate
# from "fails validation" is the whole point of the distinct exit status.
cannot_check() {
  echo "⚠️  Could not check PR #$NUMBER: $1" >&2
  exit 4
}

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || cannot_check "no repository"
SCRIPT="$REPO_DIR/validation/validate_submission.py"

command -v check-jsonschema >/dev/null 2>&1 \
  || cannot_check "check-jsonschema is not installed (pip install check-jsonschema)"

STAGE="$(mktemp -d)" || cannot_check "could not create a scratch directory"
trap 'rm -rf "$STAGE"' EXIT

fetch_metadata() {
  if command -v gh >/dev/null 2>&1; then
    gh api "repos/$REPO/pulls/$NUMBER" 2>&1
  else
    curl -sSf ${GITHUB_TOKEN:+-H "Authorization: token $GITHUB_TOKEN"} \
      "https://api.github.com/repos/$REPO/pulls/$NUMBER" 2>&1
  fi
}

META="$(fetch_metadata)" || cannot_check "could not read the pull request — ${META%%$'\n'*}"

FIELDS="$(printf '%s' "$META" | python3 -c '
import json, sys
try:
    pr = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
print(pr["title"])
print(pr["base"]["sha"])
print(pr["head"]["sha"])
' 2>/dev/null)" || cannot_check "unexpected response — ${META%%$'\n'*}"

TITLE="$(sed -n 1p <<<"$FIELDS")"
BASE="$(sed -n 2p <<<"$FIELDS")"
HEAD_SHA="$(sed -n 3p <<<"$FIELDS")"
PR_BODY="$(printf '%s' "$META" | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["body"] or "")')"

# The title is attacker-controlled and goes straight to a terminal. Without this a
# title carrying ESC can erase the line it printed on and repaint a forged verdict.
TITLE="$(printf '%s' "$TITLE" | LC_ALL=C tr -d '\000-\037\177')"
echo "PR #$NUMBER — $TITLE"
echo

# Fetch the head as data — never checked out, never executed. Deliberately fetched
# without a destination refspec: that leaves no ref behind in your clone, and the
# commit is then addressed by its own SHA, so this checks exactly the commit GitHub
# reported rather than whatever a named ref happens to point at.
git -C "$REPO_DIR" fetch --quiet --no-tags origin \
  || cannot_check "could not fetch from origin"
git -C "$REPO_DIR" fetch --quiet --no-tags "https://github.com/$REPO" \
  "pull/$NUMBER/head" \
  || cannot_check "could not fetch the pull request head"
git -C "$REPO_DIR" cat-file -e "${HEAD_SHA}^{commit}" 2>/dev/null \
  || cannot_check "the pull request head $HEAD_SHA did not arrive"
git -C "$REPO_DIR" cat-file -e "${BASE}^{commit}" 2>/dev/null || BASE="origin/main"

STATUS=0

# 1. Everything the schema cannot express.
# env -u PR_LABELS: an inherited PR_LABELS='["skip-validation"]' would otherwise make
# this print ✅ without looking at the file. Labels are a CI input, not a local one.
env -u PR_LABELS PR_BODY="$PR_BODY" python3 "$SCRIPT" inspect \
  --base "$BASE" --head "$HEAD_SHA" --stage-dir "$STAGE"
case $? in
  0) ;;
  1) STATUS=1 ;;
  # argparse errors (2) and crashes mean our tooling is broken, not their submission.
  *) cannot_check "the validator could not run — is PyYAML installed?" ;;
esac

# 2. The submission format itself, if step 1 got far enough to stage a file.
if [[ -f "$STAGE/result.json" ]]; then
  # Read by key from JSON, never by word position: the previous `read -r A B C` split
  # on spaces, so a clone under "~/My Repos" — or a submission whose name contains a
  # space — silently scrambled the fields and failed every valid submission.
  SCHEMA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("schema_path",""))' "$STAGE/result.json")" \
    || cannot_check "could not read the staged result"
  TARGET="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("display_path",""))' "$STAGE/result.json")"
  SHOWN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("schema_display",""))' "$STAGE/result.json")"
  # No name allowlist here on purpose. check_filename is terminal now, so a name that
  # failed the rule never reaches staging and never appears in result.json — the guard
  # this block used to carry protected against something that can no longer happen.
  if [[ -n "$SCHEMA" && -n "$TARGET" ]]; then
    echo "--- check-jsonschema --schemafile $SHOWN $TARGET"
    (cd "$STAGE" && check-jsonschema --schemafile "$SCHEMA" "$TARGET") || STATUS=1
  fi
fi

echo
if [[ $STATUS -eq 0 ]]; then
  echo "✅  PR #$NUMBER passes validation — well-formed, and worth reviewing."
else
  echo "❌  PR #$NUMBER fails validation — see above. Nothing was posted to the pull request."
fi
exit $STATUS
