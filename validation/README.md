# Submission validation

Every pull request that touches `submissions/` is checked automatically, and again after each change you push. The check is mechanical:
it confirms your file is well-formed and follows the
[submission format](../SUBMISSION_FORMAT.md). It does not judge the metric itself —
that is what reviewers do, once the check is green.

Everything it runs is in this directory, and you can run all of it yourself before
opening a pull request.

## What it checks

| | Checked | If it is wrong |
|---|---|---|
| **The pull request** | Adds exactly one file under `submissions/`, and changes nothing else | error |
| **The file name** | `lowercase-with-hyphens.yml`, named after the metric | error |
| **The file** | Parses as YAML, declares a `schema_version` this repository knows, is a reasonable size | error |
| **The fields** | Required keys present, correct types, controlled vocabularies spelled exactly, no template placeholders left in | error |
| **The description** | Keeps the checklist from the pull request template, with every box ticked | error |
| | The file name resembles the metric name; the pull request edits a submission that is already merged | warning |

Errors fail the check. Warnings do not — they are shown to reviewers as notes.

## Run it yourself

```sh
pip install "PyYAML~=6.0" check-jsonschema

# 1. everything the format schema cannot express
python3 validation/validate_submission.py inspect --files submissions/my-metric.yml

# 2. the format itself — this is the exact command the repository runs
check-jsonschema --schemafile validation/schemas/v1.json submissions/my-metric.yml
```

If a message from step 2 is hard to read, pipe it back for line numbers and
suggestions for near-miss values:

```sh
check-jsonschema --schemafile validation/schemas/v1.json \
    submissions/my-metric.yml --output-format json \
  | python3 validation/validate_submission.py explain -
```

With [uv](https://docs.astral.sh/uv/), no install step is needed at all — the script
declares its own dependency:

```sh
uv run validation/validate_submission.py inspect --files submissions/my-metric.yml
```

`--help` on the script, or on either of its commands, prints the same walkthrough.

The equivalent uv command to run the check-jsonschema step is:

```sh
uv run --with=check-jsonschema -- check-jsonschema --schemafile validation/schemas/v1.json submissions/my-metric.yml
```


## What is in here

| File | What it is |
|---|---|
| `schemas/v1.json` | The submission format, machine-readable. One file per **major** format version, so a file written against `1.x` keeps validating after the format moves on. |
| `validate_submission.py` | The checks a schema cannot express, plus the explainer for step 2's output. |

The workflow that runs these on your pull request is
[`.github/workflows/validate-submission.yml`](../.github/workflows/validate-submission.yml).

Something reported here that you think is wrong, or a message you could not act on?
That is worth an [issue](../../issues) — the check is new, and its wording is still
being improved.
