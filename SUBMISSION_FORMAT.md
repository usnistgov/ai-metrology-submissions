# Submission format

A submission is **one YAML file describing one metric or measurement methodology**,
added under `submissions/`. Name the file after the metric, in lowercase with hyphens:
`submissions/<metric-name>.yml` (e.g. `submissions/toxicity-score.yml`).

**Six keys are required:** `name`, `applied_definition`, `submitter_organizations`,
`contact_email`, `references`, `implementation_resources`. Everything else is
optional — include what you can, and delete optional keys that don't apply.

The fastest way to start is to copy the [template](#template) below or one of the
worked [example submissions](../../pulls?q=is%3Apr+label%3Aexample-submission), which
show two completed submissions end to end.

> **Do not submit proprietary or confidential information** — any content posted is
> considered public disclosure and non-confidential.

## Fields

The **Type** column tells you how to write the value in YAML:

- **text** — a single value on the key's line (or a `|` block for longer text).
- **list** — one or more entries, each on its own line starting with `- `.
- **list of allowed values** — a list whose entries must come from the values named
  in the Description column, spelled exactly as shown.

### Section 1 — Identification and attribution

| Field | Key | Required | Type | Description |
|---|---|---|---|---|
| Name | `name` | **yes** | text | Formal name of the quantitative/qualitative measure or measurement methodology. |
| Applied Definition | `applied_definition` | **yes** | text (Markdown + LaTeX) | Precise mathematical or textual description of the metric or measurement method. Use LaTeX (`$$...$$`) for formulas. |
| Submitter Organization(s) | `submitter_organizations` | **yes** | list | The entity or institution responsible for the submission — one entry per organization. |
| Contact Email | `contact_email` | **yes** | text (email address) | Professional point of contact for verification. |

### Section 2 — Context and limitations

| Field | Key | Required | Type | Description |
|---|---|---|---|---|
| AI RMF Characteristic(s) | `ai_rmf_characteristics` | no | list of allowed values | Target [AI RMF](https://airc.nist.gov/airmf-resources/airmf/) trustworthy characteristic(s): `Valid & Reliable`, `Safe`, `Secure & Resilient`, `Accountable & Transparent`, `Explainable & Interpretable`, `Privacy-Enhanced`, `Fair`, `Accurate & Bias-Managed`. |
| Primary TEVV Application | `primary_tevv_application` | no | list of allowed values | Methodology, tool type, or mathematical approach: `Adversarial Robustness Evaluation`, `Red Teaming Evaluation Method`, `Automated Language Model Red Teaming Toolkit`, `Facial Recognition Benchmark Evaluation`, `Human-Centered Evaluation`, `Interpretability & Explanation Evaluation`, `Language Model Benchmark Evaluation`, `Object Recognition Benchmark Evaluation`, `Privacy & Security Evaluation`, `Tabular Data Benchmark Evaluation`. |
| AI Lifecycle Stage | `ai_lifecycle_stages` | no | list of allowed values | Phase(s) in the AI lifecycle where the metric or method is applied, one stage per entry: `Plan and Design`, `Collect & Process Data`, `Build`, `Use`, `Deploy`, `Operate & Monitor`. |
| Object of Measurement | `object_of_measurement` | no | list of allowed values | The entity evaluated: `agent`, `task`, `data`, `model`, `system`, `user`. |
| Model Specificity | `model_specificity` | no | text | Either `model agnostic`, or `model specific` plus which architectures (e.g. `model specific — LLMs`). |
| Domain Specificity | `domain_specificity` | no | text | Either `domain agnostic`, or `domain specific` plus which domain(s) — e.g. Finance, Healthcare, Education, Journalism, Employment (as in `domain specific — Healthcare`). |
| Usage Details | `usage_details` | no | text | Details or scenarios where the metric or method provides the most value. |
| Known Failure Modes | `known_failure_modes` | no | text | Scenarios where the metric or method may be misleading or easily "gamed." |
| Modality | `modality` | no | list of allowed values | Primary input data category: `text`, `vision`, `video`, `audio`, `structured data` (e.g., tables or knowledge bases), `physical`, `others`. |

### Section 3 — Provenance, tooling, and requirements

| Field | Key | Required | Type | Description |
|---|---|---|---|---|
| Reference(s) | `references` | **yes** | list | Citations of peer-reviewed literature or NIST resources — one entry per citation, with URLs where possible. |
| Implementation Resources | `implementation_resources` | **yes** | list | Links to software, data, or other online resources that implement the measurement approach (e.g. a Python library, GitHub, Hugging Face). |
| Common Variants | `common_variants` | no | list | Related versions of the metric (e.g. Fβ score (F0.5, F2); ROUGE-1, ROUGE-2, ROUGE-L). |
| Related Metrics | `related_metrics` | no | list | Complementary metrics to be measured in tandem. |
| Computational Requirements | `computational_requirements` | no | text | Hardware or environment needs (e.g. GPU, VRAM, specific libraries). |
| Usage Rights | `usage_rights` | no | text | Licensing or permissions (e.g. Open Source, Creative Commons). |

## Template

Copy this into `submissions/<metric-name>.yml` and follow the comments — they explain
everything, and you may keep or delete them.

```yaml
# ---------------------------------------------------------------------------
# Metric submission template — see SUBMISSION_FORMAT.md for field details.
#
# How to fill this in:
#   * Replace every <angle-bracket placeholder>, brackets included, with your
#     own content. Values shown without brackets (such as "Safe") are valid
#     sample choices — replace them with the allowed values that fit.
#   * Delete any optional key that does not apply to your metric.
#   * "|" keeps the indented lines below it as multi-line text; ">-" joins
#     them into a single line. Either way, indent the text by two spaces.
#   * If a value contains a colon followed by a space (common in citation
#     titles), wrap the value in "double quotes" or use a ">-" block.
# ---------------------------------------------------------------------------

# --- Section 1: Identification and attribution (all four keys required) ---
name: <formal name of the metric or measurement methodology>
applied_definition: |
  <precise mathematical or textual description — Markdown, with LaTeX for
  formulas, e.g. $$F_1 = 2 \cdot \frac{P \cdot R}{P + R}$$>
submitter_organizations:      # one "- " entry per organization
  - <organization name>
contact_email: <name@example.org>

# --- Section 2: Context and limitations (all optional — delete unused keys) ---
ai_rmf_characteristics:       # allowed values: see field table
  - Safe
primary_tevv_application:     # allowed values: see field table
  - Language Model Benchmark Evaluation
ai_lifecycle_stages:          # allowed values: see field table; one stage per entry
  - Build
  - Deploy
object_of_measurement:        # allowed values: see field table
  - model
model_specificity: model agnostic     # or: model specific — <which architectures>
domain_specificity: domain agnostic   # or: domain specific — <which domain(s)>
usage_details: |
  <details or scenarios where the metric or method provides the most value>
known_failure_modes: |
  <scenarios where it may be misleading or easily "gamed">
modality:                     # allowed values: see field table
  - text

# --- Section 3: Provenance, tooling, and requirements ---
references:                   # required; one "- " entry per citation
  - >-
    <citation to peer-reviewed literature or NIST resources, with a URL
    where possible>
implementation_resources:     # required; one "- " entry per link
  - <URL to software, dataset, or other implementation resource>
common_variants:              # optional
  - <related variant name>
related_metrics:              # optional
  - <complementary metric name>
computational_requirements: <hardware or environment needs>   # optional
usage_rights: <license or permissions, e.g. Apache License 2.0>   # optional
```
