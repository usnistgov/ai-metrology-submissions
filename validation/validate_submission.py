#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["PyYAML~=6.0"]
# ///
"""Check everything about a metric submission that a JSON Schema cannot.

The dependency block above is PEP 723 inline script metadata, so this file can be run
without setting anything up first:

    uv run validation/validate_submission.py inspect --files submissions/x.yml

Without `uv`, `pip install "PyYAML~=6.0"` first and run it with `python3`.

Conformance to the schema is *not* done here. The workflow runs `check-jsonschema` as
its own step, so a failing submission shows the real command and its real output. This
script runs either side of that step:

    inspect  which files the pull request touches, the filename, YAML syntax, the
             schema version, the pull request description — then stages the file for
             the schema step
    explain  turns that step's JSON output into a report, adding "did you mean" hints

Locally, both halves are two plain commands:

    python3 validation/validate_submission.py inspect --files submissions/x.yml
    check-jsonschema --schemafile validation/schemas/v1.json submissions/x.yml

SECURITY INVARIANT — this script only ever *reads* submission content; it never imports,
executes or evaluates it. It writes the submission to the runner's scratch directory for
the schema step, never into the repository. The CI job runs under
`pull_request_target`, which means it runs with repository context, so treat every
byte that comes from a pull request as hostile data. In particular: submission files
are read with `git show` into memory rather than checked out, YAML is parsed with a
loader that refuses aliases, and the pull request description reaches this script
through an environment variable rather than a shell interpolation.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import yaml

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
REPO_ROOT = Path(__file__).resolve().parents[1]

SUBMISSIONS_PREFIX = "submissions/"

# Everything under `submissions/` is somebody's submission except the README that
# explains the directory. Deciding that on the *extension* instead would mean a file
# named `submissions/my-metric` — no extension, or `.txt`, or `.yml.txt` — made the
# pull request look like a docs change, so the whole check skipped it and reported
# "nothing to validate". The filename rule is exactly what should catch that, and it
# never ran. Anything that is not the README is a submission attempt, whatever it is
# called, and is reported against as one.
SUBMISSIONS_EXEMPT = frozenset({"README.md"})

# A submission is a page of text. Anything much larger is a mistake or an attack, and
# refusing it early keeps a hostile file from ever reaching the YAML parser.
MAX_FILE_BYTES = 200 * 1024

# Maintainers can set this label to wave a pull request past these checks — for example
# the dedicated pull request that migrates merged submissions to a new major format
# version, which legitimately touches many files at once. Only users with write access
# can apply labels, so submitters cannot bypass their own validation.
BYPASS_LABEL = "skip-validation"

MAX_REPORTED_PROBLEMS = 30

FILENAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.(?:yml|yaml)$")
SCHEMA_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")
TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:")
CHECKBOX_RE = re.compile(r"^[ \t]*[-*][ \t]+\[([ xX])\][ \t]*(.*)$", re.MULTILINE)

# Angle-bracketed text containing a space: `<formal name of the metric>` is a template
# placeholder, while `<b>` or `<0.5` are not.
PLACEHOLDER_RE = re.compile(r"<[^<>\n]*\s[^<>\n]*>")

TEMPLATE_LEFTOVERS = ("[!TIP]", "Replace this box", "Guidance for submitters")

ALIAS_REFUSED = "YAML aliases (`*name`) are not allowed in submissions"

# What `schema_version` was called until 2026-08-12. Files written against the old
# template still carry it, so it is worth naming in the error rather than letting the
# schema report an unknown key and a missing one.
RENAMED_VERSION_KEY = "format_version"

REPO_URL = "https://github.com/usnistgov/didactic-rotary-phone"
FORMAT_DOC = f"{REPO_URL}/blob/main/SUBMISSION_FORMAT.md"
GUIDE_DOC = f"{REPO_URL}/blob/main/CONTRIBUTING.md"


# --------------------------------------------------------------------------------
# Findings and reporting
# --------------------------------------------------------------------------------


@dataclass
class Finding:
    """One problem to report. `level` is a GitHub annotation level."""

    level: str  # "error" or "warning"
    message: str
    file: str | None = None
    line: int | None = None


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    headline: str | None = None

    def error(self, message: str, file: str | None = None, line: int | None = None):
        self.findings.append(Finding("error", message, file, line))

    def warning(self, message: str, file: str | None = None, line: int | None = None):
        self.findings.append(Finding("warning", message, file, line))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warning"]


def emit_annotations(report: Report) -> None:
    """Emit GitHub workflow annotations, which surface on the run page."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    for finding in report.findings[:MAX_REPORTED_PROBLEMS]:
        params = []
        if finding.file:
            params.append(f"file={finding.file}")
        if finding.line:
            params.append(f"line={finding.line}")
        # Annotation messages are single-line; newlines must be escaped.
        text = finding.message.replace("\n", "%0A")
        joined = ",".join(params)
        prefix = f"::{finding.level} {joined}::" if params else f"::{finding.level}::"
        print(prefix + text)


def render_report(report: Report) -> str:
    """Render the Markdown shown in the job summary and printed to the console."""
    lines = ["## Submission validation", ""]

    if report.headline:
        lines += [report.headline, ""]
    elif report.errors:
        counts = f"{plural(len(report.errors), 'problem')}"
        if report.warnings:
            counts += f" and {plural(len(report.warnings), 'warning')}"
        if os.environ.get("GITHUB_ACTIONS"):
            advice = (
                "This pull request is not ready for review yet — fix the points below "
                "and push to your fork, and this check runs again automatically."
            )
        else:
            advice = "Fix the points below, then run this again."
        lines += [f"❌ **{counts} found.** {advice}", ""]
    elif report.warnings:
        lines += [
            f"✅ **Passed**, with {plural(len(report.warnings), 'note')} for reviewers.",
            "",
        ]
    else:
        lines += ["✅ **Passed.** Nothing further is needed from you.", ""]

    if report.checked:
        checked = ", ".join(f"`{path}`" for path in report.checked)
        lines += [f"Checked: {checked}", ""]

    if report.findings:
        lines += ["| | Problem |", "|---|---|"]
        for finding in report.findings[:MAX_REPORTED_PROBLEMS]:
            icon = "❌" if finding.level == "error" else "⚠️"
            where = ""
            if finding.file and finding.line:
                where = f"`{finding.file}` line {finding.line}<br>"
            elif finding.file:
                where = f"`{finding.file}`<br>"
            body = finding.message.replace("\n", "<br>")
            lines.append(f"| {icon} | {where}{body} |")
        if len(report.findings) > MAX_REPORTED_PROBLEMS:
            hidden = len(report.findings) - MAX_REPORTED_PROBLEMS
            lines.append(f"| | …and {plural(hidden, 'further problem')} not shown. |")
        lines += [
            "",
            f"Field reference: [SUBMISSION_FORMAT.md]({FORMAT_DOC}) · How to submit: [CONTRIBUTING.md]({GUIDE_DOC})",
        ]

    return "\n".join(lines) + "\n"


def finish(report: Report) -> int:
    emit_annotations(report)
    markdown = render_report(report)
    print(markdown)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write(markdown)
    return 1 if report.errors else 0


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


# --------------------------------------------------------------------------------
# Reading the files under validation
# --------------------------------------------------------------------------------


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


class Tree:
    """Read-only access to the revision under validation.

    `ref` is a git revision (CI), or None to read the working directory (local use).
    """

    def __init__(self, ref: str | None = None):
        self.ref = ref

    def read(self, path: str) -> bytes:
        if self.ref is None:
            return Path(path).read_bytes()
        result = subprocess.run(
            ["git", "show", f"{self.ref}:{path}"],
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", "replace").strip())
        return result.stdout

    def is_symlink(self, path: str) -> bool:
        if self.ref is None:
            return Path(path).is_symlink()
        entry = git("ls-tree", self.ref, "--", path).strip()
        return bool(entry) and entry.split()[0] == "120000"


def changed_files(base: str, head: str) -> list[tuple[str, str]]:
    """Return (status, path) for the changes this pull request makes.

    `base...head` is the same diff GitHub shows in the Files changed tab: what the
    branch adds relative to where it forked, not everything that landed on main since.
    """
    raw = git("diff", "--name-status", "--no-renames", "-z", f"{base}...{head}")
    fields = [item for item in raw.split("\0") if item]
    return list(zip(fields[0::2], fields[1::2]))


class SubmissionLoader(yaml.SafeLoader):
    """SafeLoader that additionally refuses YAML aliases.

    A submission has no legitimate use for `*aliases`, and a one-kilobyte file full of
    them expands into gigabytes (the "billion laughs" attack), which would take the
    runner down before any check got to run.
    """

    def compose_node(self, parent, index):
        if self.check_event(yaml.events.AliasEvent):
            event = self.peek_event()
            raise yaml.composer.ComposerError(
                None,
                None,
                ALIAS_REFUSED,
                event.start_mark,
            )
        return super().compose_node(parent, index)


def top_level_key_lines(text: str) -> dict[str, int]:
    """Map each top-level YAML key to its 1-based line, for annotation anchoring."""
    lines: dict[str, int] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        match = TOP_LEVEL_KEY_RE.match(line)
        if match and match.group(1) not in lines:
            lines[match.group(1)] = number
    return lines


# --------------------------------------------------------------------------------
# Reading check-jsonschema's output
#
# This script does not run check-jsonschema. The workflow does, as its own visible
# step, so that a failing submission shows the real command and its real output —
# the same command a submitter can run locally. All that happens here is turning
# that command's JSON output into a report.
# --------------------------------------------------------------------------------


def property_from_path(path: str) -> str | None:
    """`$.modality[0]` -> `modality`. The top-level key is what a submitter edits."""
    match = re.match(r"^\$\.([A-Za-z_][A-Za-z0-9_]*)", path or "")
    return match.group(1) if match else None


def readable(error: dict, schema: dict) -> str:
    """Post-process one check-jsonschema error into something a submitter can act on.

    Deliberately thin: it adds a "did you mean" hint to the two mistakes submitters
    actually make — a value outside a controlled vocabulary, and a misspelled key —
    and rewrites the one message that is unusable as-is. Everything else keeps
    check-jsonschema's own wording rather than growing a second error interpreter.
    """
    message = error.get("message", "")

    # The schema rejects template placeholders with `not: {pattern: ...}`, whose raw
    # message shows the submitter a regex. Say what it means instead.
    if " should not be valid under " in message:
        value = message.split(" should not be valid under ")[0]
        return (
            f"{value} is placeholder text from the template. Replace the part in angle brackets with your own content."
        )

    # A misspelled key: "Additional properties are not allowed ('contact_emails' ...)"
    if message.startswith("Additional properties are not allowed"):
        known = list(schema.get("properties", {}))
        hints = []
        for name in re.findall(r"'([^']+)'", message):
            close = get_close_matches(name, known, n=1, cutoff=0.7)
            if close:
                hints.append(f"`{name}` → did you mean `{close[0]}`?")
        return message + (("  " + "; ".join(hints)) if hints else "")

    # A value outside a controlled vocabulary: "'Text' is not one of ['text', ...]"
    match = re.match(r"^(.*?) is not one of \[", message)
    if match:
        allowed = enum_values_at(schema, property_from_path(error.get("path", "")))
        try:
            given = str(ast.literal_eval(match.group(1)))
        except (ValueError, SyntaxError):
            return message
        close = get_close_matches(given, allowed, n=1, cutoff=0.4)
        if close:
            return message + f"  Did you mean `{close[0]}`?"

    return message


def enum_values_at(schema: dict, prop: str | None) -> list[str]:
    """The allowed values for a property, whether the enum is on it or on its items."""
    node = schema.get("properties", {}).get(prop or "", {})
    enum = node.get("enum") or node.get("items", {}).get("enum") or []
    return [str(value) for value in enum]


def describe_value(value: Any) -> str:
    if value is None:
        return "nothing"
    if isinstance(value, bool):
        return "true/false"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "a mapping"
    if isinstance(value, (int, float)):
        return "a number"
    return type(value).__name__


# --------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------


def is_submission_path(path: str) -> bool:
    """Is this path a submission? See `SUBMISSIONS_EXEMPT` for why not by name."""
    if not path.startswith(SUBMISSIONS_PREFIX):
        return False
    return path[len(SUBMISSIONS_PREFIX) :] not in SUBMISSIONS_EXEMPT


def check_changed_paths(changes: list[tuple[str, str]], report: Report) -> list[str]:
    """Decide whether this is a submission pull request, and police what it touches.

    Returns the submission files to validate. An empty list means "not a submission
    pull request" — a docs or maintenance change, which this check leaves alone so it
    stays safe to require on every pull request.
    """
    submissions = [path for _status, path in changes if is_submission_path(path)]
    if not submissions:
        return []

    others = sorted({path for _status, path in changes} - set(submissions))
    if others:
        listed = ", ".join(f"`{path}`" for path in others[:8])
        if len(others) > 8:
            listed += f", and {len(others) - 8} more"
        report.error(
            "A submission pull request must contain nothing but the submission file "
            f"itself. This one also changes {listed}. Please remove those changes and "
            "open a separate pull request for them.",
        )

    if len(submissions) > 1:
        listed = ", ".join(f"`{path}`" for path in submissions)
        report.error(
            f"This pull request adds {len(submissions)} submission files ({listed}), "
            "but each pull request must submit exactly one metric or measurement "
            "method. Please split them up.",
        )

    for status, path in changes:
        if path not in submissions:
            continue
        if status.startswith("D"):
            report.error(
                f"This pull request deletes `{path}`. Merged submissions are not "
                "removed through the submission process — please raise an issue "
                "instead.",
                file=path,
            )
        elif status.startswith("M"):
            report.warning(
                f"This pull request modifies `{path}`, which is an already-merged "
                "submission, rather than adding a new one. Reviewers should confirm "
                "the change is intended and comes from the original submitter.",
                file=path,
            )

    for path in submissions:
        relative = path[len(SUBMISSIONS_PREFIX) :]
        if "/" in relative:
            report.error(
                f"`{path}` is in a subdirectory. A submission is a single file placed directly in `submissions/`.",
                file=path,
            )

    return submissions[:5]


def check_filename(path: str, report: Report) -> None:
    name = path[len(SUBMISSIONS_PREFIX) :].rsplit("/", maxsplit=1)[-1]
    if not FILENAME_RE.match(name):
        report.error(
            f"`{name}` is not a valid submission file name. Name the file after your "
            "metric in lowercase, with hyphens between words and a `.yml` extension — "
            "for example `submissions/jailbreak-success-rate.yml`.",
            file=path,
        )


def schema_file_for(
    data: dict,
    path: str,
    lines: dict[str, int],
    report: Report,
) -> Path | None:
    """Pick the schema for the version this file declares — one file per MAJOR."""
    version = data.get("schema_version")
    anchor = lines.get("schema_version")

    if version is None:
        if RENAMED_VERSION_KEY in data:
            # Anyone who copied the template before 2026-08-12 has the old name. Saying
            # so beats the two generic errors the schema would otherwise produce
            # ("unrecognised key" plus "missing required key").
            report.error(
                f"`{RENAMED_VERSION_KEY}` has been renamed to `schema_version`. Rename "
                "the key in your file — the value does not change.",
                file=path,
                line=lines.get(RENAMED_VERSION_KEY),
            )
            return None
        report.error(
            "Missing required key `schema_version`. Copy the current version from the "
            "template in SUBMISSION_FORMAT.md — it must be quoted, like "
            '`schema_version: "1.0"`.',
            file=path,
        )
        return None

    if not isinstance(version, str):
        # Unquoted `1.0` is read by YAML as the number 1.0, and `1.10` would silently
        # become 1.1. This is the single easiest mistake to make in the whole file.
        report.error(
            f"`schema_version` must be quoted text, but YAML read it as a number "
            f'({version}). Write it as `schema_version: "{version}"`.',
            file=path,
            line=anchor,
        )
        return None

    if not SCHEMA_VERSION_RE.match(version):
        report.error(
            f'`schema_version` must look like `MAJOR.MINOR`, for example `"1.0"`. This file says `{version}`.',
            file=path,
            line=anchor,
        )
        return None

    major = SCHEMA_VERSION_RE.match(version).group(1)
    schema_file = SCHEMA_DIR / f"v{major}.json"
    if not schema_file.exists():
        known = sorted(f"{item.stem[1:]}.x" for item in SCHEMA_DIR.glob("v*.json"))
        report.error(
            f"`schema_version` is `{version}`, which this repository does not know how "
            f"to validate. Supported versions: {', '.join(known)}.",
            file=path,
            line=anchor,
        )
        return None

    return schema_file


def check_submission_file(
    tree: Tree,
    path: str,
    report: Report,
    stage_dir: Path | None = None,
) -> Path | None:
    """Run every check a JSON Schema cannot, then stage the file for the schema step.

    Returns the staged path, or None if the file never got far enough to be worth
    validating against the schema.
    """
    check_filename(path, report)

    if tree.is_symlink(path):
        report.error(
            f"`{path}` is a symbolic link. A submission must be a regular YAML file.",
            file=path,
        )
        return None

    try:
        raw = tree.read(path)
    except (OSError, RuntimeError) as exc:
        report.error(f"Could not read `{path}`: {exc}", file=path)
        return None

    if len(raw) > MAX_FILE_BYTES:
        report.error(
            f"`{path}` is {len(raw) // 1024} KB. A submission describes one metric and "
            f"should be a few kilobytes; the limit is {MAX_FILE_BYTES // 1024} KB.",
            file=path,
        )
        return None

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        report.error(f"`{path}` is not valid UTF-8 text.", file=path)
        return None

    if "\x00" in text:
        report.error(f"`{path}` contains null bytes and is not a text file.", file=path)
        return None

    try:
        data = yaml.load(text, Loader=SubmissionLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        if problem == ALIAS_REFUSED:
            advice = f"{ALIAS_REFUSED}. Write each value out in full."
        else:
            advice = (
                f"`{path}` is not valid YAML: {problem}. A stray colon, tab, or "
                "inconsistent indentation is the usual cause; quote any value that "
                "contains a colon followed by a space."
            )
        report.error(advice, file=path, line=(mark.line + 1) if mark else None)
        return None

    if data is None:
        report.error(f"`{path}` is empty.", file=path)
        return None

    if not isinstance(data, dict):
        report.error(
            f"`{path}` must be a mapping of keys to values, like the template in "
            f"SUBMISSION_FORMAT.md, but it reads as {describe_value(data)}.",
            file=path,
        )
        return None

    non_text_keys = [key for key in data if not isinstance(key, str)]
    if non_text_keys:
        # YAML turns bare `yes`, `no`, `on` and `off` into booleans, keys included.
        report.error(
            f"`{path}` has keys that are not text: {non_text_keys}. Quote them.",
            file=path,
        )
        return None

    lines = top_level_key_lines(text)
    report.checked.append(path)
    check_name_matches_filename(data, path, report)

    # Everything above is what a JSON Schema cannot express. Conformance to the schema
    # itself is the workflow's next step; hand it the file and the schema to use.
    schema_file = schema_file_for(data, path, lines, report)
    if schema_file is None:
        return None
    return stage_for_schema_check(path, text, schema_file, stage_dir)


def stage_for_schema_check(
    path: str,
    text: str,
    schema_file: Path,
    stage_dir: Path | None,
) -> Path:
    """Write the submission where the check-jsonschema step can read it.

    Under `pull_request_target` the pull request is never checked out, so the file has
    to be materialised somewhere for the next step. It goes to the runner's scratch
    directory, outside the repository, under the name the submitter chose.

    It is staged under the same relative path it has in the repository, so the schema
    step can run from the staging directory and report `submissions/my-metric.yml` —
    character for character what the submitter sees running the command themselves.

    Returns the schema to validate against, whether or not anything was staged.
    """
    if stage_dir is not None:
        # A badly named file still gets staged — `check_filename` reports it but does
        # not stop, and since the path check stopped going by extension the name is
        # not known to be well-formed here. It cannot escape the staging directory
        # regardless: git tree entries never contain a `..` component, the caller has
        # already rejected anything with a separator after `submissions/`, and only
        # the basename is used.
        staged = stage_dir / SUBMISSIONS_PREFIX.strip("/") / Path(path).name
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_text(text, encoding="utf-8")
        (stage_dir / "context.json").write_text(
            json.dumps(
                {
                    "display_path": path,
                    "staged_path": str(staged),
                    "schema_path": str(schema_file),
                    "schema_display": schema_display(schema_file),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return schema_file


def schema_display(schema_file: Path) -> str:
    """The schema's repo-relative path — what a submitter types, not a runner path."""
    try:
        return str(schema_file.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(schema_file)


def check_name_matches_filename(data: dict, path: str, report: Report) -> None:
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return
    if PLACEHOLDER_RE.search(name):
        return  # already reported as an unreplaced placeholder; do not pile on
    stem = Path(path).stem

    def tokens(value: str) -> set[str]:
        return {token for token in re.split(r"[^a-z0-9]+", value.lower()) if token}

    if not tokens(stem) & tokens(name):
        report.warning(
            f"The file is named `{stem}` but the metric is called “{name}”. "
            "Submissions are normally named after the metric; reviewers may ask "
            "you to rename it.",
            file=path,
        )


def check_pull_request_body(body: str, report: Report) -> None:
    if not body.strip():
        report.error(
            "The pull request description is empty. It should follow the template that "
            "is pre-filled when you open a pull request, including the checklist.",
        )
        return

    boxes = CHECKBOX_RE.findall(body)
    if not boxes:
        report.error(
            "The pull request description does not contain the checklist from the "
            "template. Please restore it and tick each item — reviewers rely on it, "
            "particularly the confirmation that the submission holds nothing "
            "proprietary or confidential.",
        )
        return

    unticked = [label.strip() for mark, label in boxes if mark == " "]
    if unticked:
        shown = "\n".join(f"• {item[:110]}" for item in unticked[:6])
        report.error(
            f"{plural(len(unticked), 'checklist item')} in the pull request "
            f"description {'is' if len(unticked) == 1 else 'are'} not ticked:\n"
            f"{shown}\nEdit the description and tick each box once it is true.",
        )

    if any(marker in body for marker in TEMPLATE_LEFTOVERS):
        report.warning(
            "The pull request description still contains the guidance boxes from the "
            "template. They are meant to be deleted once you have filled the "
            "description in.",
        )


# --------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------


def parse_labels(raw: str) -> set[str]:
    try:
        return {str(label) for label in json.loads(raw)}
    except (ValueError, TypeError):
        return set()


def emit_output(name: str, value: str) -> None:
    """Publish a step output for the workflow to act on."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def stage_inspect(args) -> int:
    """Everything a JSON Schema cannot check, and hand off to the schema step."""
    report = Report()

    if BYPASS_LABEL in parse_labels(os.environ.get("PR_LABELS", "")):
        report.headline = f"⏭️ **Skipped** — a maintainer has applied the `{BYPASS_LABEL}` label to this pull request."
        emit_output("validate", "false")
        return finish(report)

    if args.files:
        tree = Tree()
        changes = [("A", path) for path in args.files]
    else:
        tree = Tree(args.head)
        try:
            changes = changed_files(args.base, args.head)
        except RuntimeError as exc:
            report.error(f"Could not work out what this pull request changes: {exc}")
            emit_output("validate", "false")
            return finish(report)

    submissions = check_changed_paths(changes, report)

    if not submissions:
        report.headline = (
            "⏭️ **Nothing to validate** — this pull request does not add or change a submission under `submissions/`."
        )
        emit_output("validate", "false")
        return finish(report)

    body = os.environ.get("PR_BODY")
    if body is not None:
        check_pull_request_body(body, report)

    stage_dir = Path(args.stage_dir) if args.stage_dir else None
    schema_file = None
    for path in submissions:
        found = check_submission_file(tree, path, report, stage_dir)
        schema_file = found or schema_file

    context_file = stage_dir / "context.json" if stage_dir else None
    ready = bool(schema_file) and not report.errors
    emit_output("validate", "true" if ready else "false")
    if ready and context_file and context_file.exists():
        context = json.loads(context_file.read_text(encoding="utf-8"))
        emit_output("workdir", str(stage_dir))
        emit_output("schema", context["schema_path"])
        emit_output("schema_display", context["schema_display"])
        emit_output("file", context["display_path"])

    code = finish(report)

    if ready and stage_dir is None:
        # Local run: the schema check is a separate command here too, by design —
        # the same one the workflow runs, so local and CI cannot drift apart.
        print(
            "Next, check it against the schema:\n\n"
            f"    check-jsonschema --schemafile {schema_display(schema_file)} "
            f"{submissions[0]}\n",
        )

    return code


def infer_schema_file(text: str) -> Path | None:
    """Work out which schema applies from the file's own `schema_version`."""
    try:
        data = yaml.load(text, Loader=SubmissionLoader)
    except yaml.YAMLError:
        return None
    version = data.get("schema_version") if isinstance(data, dict) else None
    match = SCHEMA_VERSION_RE.match(version) if isinstance(version, str) else None
    if not match:
        return None
    candidate = SCHEMA_DIR / f"v{match.group(1)}.json"
    return candidate if candidate.exists() else None


def stage_explain(args) -> int:
    """Turn the JSON from `check-jsonschema --output-format json` into a report."""
    report = Report()

    from_stdin = args.errors == "-"
    errors_file = Path(args.errors)
    if not from_stdin and not errors_file.exists():
        print(
            f"No such file: {errors_file}\n\n"
            "Produce it by running check-jsonschema with JSON output, for example:\n"
            "    check-jsonschema --schemafile validation/schemas/v1.json \\\n"
            f"        submissions/<name>.yml --output-format json > {errors_file}\n\n"
            "Or pipe it straight in, with `-` in place of the file name.",
            file=sys.stderr,
        )
        return 2

    source_name = "the piped input" if from_stdin else str(errors_file)
    try:
        raw = sys.stdin.read() if from_stdin else errors_file.read_text(encoding="utf-8")
        payload = json.loads(raw)
        # Reporting "no errors" for a file that is simply the wrong shape would be a
        # false all-clear, so require the keys check-jsonschema actually writes.
        recognised = isinstance(payload, dict) and {"status", "errors"} & set(payload)
    except ValueError:
        recognised = False
    if not recognised:
        print(
            f"{source_name} is not the JSON that check-jsonschema produces. Re-run it with --output-format json.",
            file=sys.stderr,
        )
        return 2
    errors = payload.get("errors", [])

    if not errors:
        print(f"Nothing to explain — {source_name} reports no schema errors.")
        return 0

    # In CI the inspect step leaves a context file naming the staged copy; run by hand
    # there is no such file, and check-jsonschema's own output names the file instead.
    context = {}
    if args.stage_dir:
        context_file = Path(args.stage_dir) / "context.json"
        if context_file.exists():
            context = json.loads(context_file.read_text(encoding="utf-8"))

    display_path = context.get("display_path") or errors[0].get("filename") or "?"
    source = Path(context.get("staged_path") or errors[0].get("filename") or "")

    text = ""
    if source.is_file():
        try:
            text = source.read_text(encoding="utf-8")
        except OSError:
            text = ""
    lines = top_level_key_lines(text)

    schema_path = None
    for candidate in (context.get("schema_path"), args.schemafile):
        if candidate:
            schema_path = Path(candidate)
            break
    if schema_path is None and text:
        schema_path = infer_schema_file(text)

    schema = {}
    if schema_path and schema_path.is_file():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    else:
        # Without the schema the messages still stand; only the suggestions are lost.
        report.warning(
            "Could not work out which schema was used, so near-miss suggestions are "
            "not shown. Pass --schemafile to get them.",
        )

    report.checked.append(display_path)
    for error in errors:
        key = property_from_path(error.get("path", ""))
        if key is None:
            # A whole-file error such as a missing or misspelled key names it instead.
            named = re.findall(r"'([^']+)'", error.get("message", ""))
            key = next((name for name in named if name in lines), None)
        report.error(
            readable(error, schema),
            file=display_path,
            line=lines.get(key) if key else None,
        )

    return finish(report)


PROG = "python3 validation/validate_submission.py"

OVERVIEW = """\
Check a metric submission for the NIST AI Metrology Center before opening a pull
request, using the same checks the repository runs.

Whether the file matches the submission format is checked by `check-jsonschema`, a
separate tool, so that you can run exactly what the repository runs. This script
covers everything that a format schema cannot express, and explains the results.
"""

WALKTHROUGH = f"""\
checking a submission, start to finish:

  pip install "PyYAML~=6.0" check-jsonschema

  # 1. the things the format schema cannot check
  {PROG} inspect --files submissions/my-metric.yml

  # 2. the format itself — this is the command the repository runs
  check-jsonschema --schemafile validation/schemas/v1.json \\
      submissions/my-metric.yml

  # 3. optional: repeat step 2 as JSON, and explain it with suggestions
  check-jsonschema --schemafile validation/schemas/v1.json \\
      submissions/my-metric.yml --output-format json > schema-errors.json
  {PROG} explain

Field reference: SUBMISSION_FORMAT.md   How to submit: CONTRIBUTING.md
"""

INSPECT_DESCRIPTION = """\
Check everything about a submission that the format schema cannot express: that the
pull request adds exactly one YAML file under submissions/, that nothing else is
touched, that the file is named after the metric in lowercase-with-hyphens, that it
parses as YAML, that it declares a schema version this repository knows, and that
the pull request description still carries its checklist.

It does NOT check the fields themselves — run check-jsonschema for that, as shown
below.
"""

INSPECT_EXAMPLES = f"""\
examples:

  # a file in your own fork
  {PROG} inspect --files submissions/my-metric.yml

  # what a pull request changes, as CI runs it
  {PROG} inspect --base <base-sha> --head <head-ref>
"""

EXPLAIN_DESCRIPTION = """\
Re-read the errors that check-jsonschema found and print them with line numbers and
"did you mean" suggestions for near-miss values and misspelled keys.

Reads schema-errors.json in the current directory unless you name another file, or
`-` to read from a pipe.
"""

EXPLAIN_EXAMPLES = f"""\
examples:

  # straight through, without leaving a file behind
  check-jsonschema --schemafile validation/schemas/v1.json \\
      submissions/my-metric.yml --output-format json | {PROG} explain -

  # or save it first, and explain the default file name
  check-jsonschema --schemafile validation/schemas/v1.json \\
      submissions/my-metric.yml --output-format json > schema-errors.json
  {PROG} explain

  # or from a file you named yourself
  {PROG} explain build/my-errors.json
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=OVERVIEW,
        epilog=WALKTHROUGH,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    stages = parser.add_subparsers(dest="stage", required=True, metavar="COMMAND")

    inspect = stages.add_parser(
        "inspect",
        help="check what the schema cannot: files touched, file name, YAML syntax",
        description=INSPECT_DESCRIPTION,
        epilog=INSPECT_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    inspect.add_argument(
        "--files",
        nargs="+",
        metavar="PATH",
        help="submission file(s) to check, relative to the repository root",
    )
    inspect.add_argument(
        "--base",
        metavar="REV",
        help="base revision of a pull request (instead of --files)",
    )
    inspect.add_argument(
        "--head",
        metavar="REV",
        default="HEAD",
        help="revision to check against --base (default: HEAD)",
    )
    # CI plumbing: where to leave the file for the check-jsonschema step. Hidden from
    # --help because it is meaningless outside the workflow.
    inspect.add_argument("--stage-dir", metavar="DIR", help=argparse.SUPPRESS)

    explain = stages.add_parser(
        "explain",
        help="explain check-jsonschema's JSON output, with suggestions",
        description=EXPLAIN_DESCRIPTION,
        epilog=EXPLAIN_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    explain.add_argument(
        "errors",
        nargs="?",
        default="schema-errors.json",
        metavar="ERRORS_JSON",
        help="output of `check-jsonschema --output-format json`; `-` reads a pipe (default: schema-errors.json)",
    )
    explain.add_argument(
        "--schemafile",
        metavar="PATH",
        help="schema that was validated against; inferred from the file's schema_version when omitted",
    )
    explain.add_argument("--stage-dir", metavar="DIR", help=argparse.SUPPRESS)

    args = parser.parse_args(argv)

    if args.stage == "inspect":
        if not args.files and not args.base:
            inspect.error(
                "give --files to check a submission in your own copy, or --base to check what a pull request changes",
            )
        return stage_inspect(args)
    return stage_explain(args)


if __name__ == "__main__":
    sys.exit(main())
