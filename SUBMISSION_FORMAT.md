# Submission format

A submission is **one YAML file describing one metric or measurement methodology**,
added under `submissions/`. Name the file after the metric, in lowercase with hyphens:
`submissions/<metric-name>.yml` (e.g. `submissions/toxicity-score.yml`).

Six fields are **required**; everything else is optional — include what you can,
and simply omit optional fields that don't apply. Two complete worked examples are
kept open as pull requests (see the [README](README.md)).

## Fields

### Section 1 — Identification and attribution

| Field | Key | Required | Description |
|---|---|---|---|
| Name | `name` | **yes** | Formal name of the quantitative/qualitative measure or measurement methodology. |
| Applied Definition | `applied_definition` | **yes** | Precise mathematical or textual description of the metric or measurement method. Markdown; use LaTeX for formulas. |
| Submitter Organization(s) | `submitter_organizations` | **yes** | Entity or institution responsible for the submission (list). |
| Contact Email | `contact_email` | **yes** | Professional point of contact for verification. |

### Section 2 — Context and limitations (all optional)

| Field | Key | Description / allowed values |
|---|---|---|
| AI RMF Characteristic(s) | `ai_rmf_characteristics` | Target [AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) trustworthy characteristic(s). One or more of: `Valid & Reliable`, `Safe`, `Secure & Resilient`, `Accountable & Transparent`, `Explainable & Interpretable`, `Privacy-Enhanced`, `Fair`, `Accurate & Bias-Managed`. |
| Primary TEVV Application | `primary_tevv_application` | Methodology, tool type, or mathematical approach. One or more of: `Adversarial Robustness Evaluation`, `Red Teaming Evaluation Method`, `Automated Language Model Red Teaming Toolkit`, `Facial Recognition Benchmark Evaluation`, `Human-Centered Evaluation`, `Interpretability & Explanation Evaluation`, `Language Model Benchmark Evaluation`, `Object Recognition Benchmark Evaluation`, `Privacy & Security Evaluation`, `Tabular Data Benchmark Evaluation`. |
| AI Lifecycle Stage | `ai_lifecycle_stages` | Phase(s) in the AI lifecycle where the metric or method is applied. One or more of: `Plan and Design`, `Collect & Process Data`, `Build; Use`, `Build; Use; Deploy`, `Deploy; Operate & Monitor`, `Operate & Monitor` (a stage span like `Build; Use; Deploy` is a single option — keep it as one list item). |
| Object of Measurement | `object_of_measurement` | The entity evaluated. One or more of: `agent`, `task`, `data`, `model`, `system`, `user`. |
| Model Specificity | `model_specificity` | `model agnostic` or `model specific` — if specific, say for which architectures (e.g. `model specific — LLMs`). |
| Domain Specificity | `domain_specificity` | `domain agnostic`, or the applicable domain(s) (e.g. `Finance`, `Healthcare`, `Education`, `Journalism`, `Employment`). |
| Usage Details | `usage_details` | Details or scenarios where the metric or method provides the most value. |
| Known Failure Modes | `known_failure_modes` | Scenarios where the metric or method may be misleading or easily "gamed." |
| Modality | `modality` | Primary input data category. One or more of: `text`, `vision`, `video`, `audio`, `structured data`, `physical`, `others`. |

### Section 3 — Provenance, tooling, and requirements

| Field | Key | Required | Description |
|---|---|---|---|
| Reference(s) | `references` | **yes** | Reference(s) to peer-reviewed literature or NIST resources (list). |
| Implementation Resources | `implementation_resources` | **yes** | Links to software, data, or other online resources that implement the measurement approach (e.g. Python library, GitHub, Hugging Face) (list). |
| Common Variants | `common_variants` | no | Related versions of the metric (e.g. Fβ score (F0.5, F2); ROUGE-1, ROUGE-2, ROUGE-L) (list). |
| Related Metrics | `related_metrics` | no | Complementary metrics to be measured in tandem (list). |
| Computational Requirements | `computational_requirements` | no | Hardware or environment needs (e.g. GPU, VRAM, specific libraries). |
| Usage Rights | `usage_rights` | no | Licensing or permissions (e.g. Open Source, Creative Commons). |

> **Do not submit proprietary or confidential information** — any content posted is
> considered public disclosure and non-confidential.

## Template

Copy this into `submissions/<metric-name>.yml` and fill it in. Delete optional keys
you don't use. Multi-line text uses YAML block style (`|`); lists use `-` items.

```yaml
# --- Section 1: Identification and attribution (all required) ---
name: <Formal name of the metric or measurement methodology>
applied_definition: |
  <Precise mathematical or textual description. Markdown, with LaTeX for formulas,
  e.g. $$F_1 = 2 \cdot \frac{P \cdot R}{P + R}$$>
submitter_organizations:
  - <Organization name>
contact_email: <name@example.org>

# --- Section 2: Context and limitations (all optional — delete what you don't use) ---
ai_rmf_characteristics:
  - <e.g. Safe>
primary_tevv_application:
  - <e.g. Language Model Benchmark Evaluation>
ai_lifecycle_stages:
  - <e.g. Build; Use; Deploy>
object_of_measurement:
  - <e.g. model>
model_specificity: <model agnostic | model specific — say which>
domain_specificity: <domain agnostic | the domain, e.g. Healthcare>
usage_details: |
  <Where the metric or method provides the most value.>
known_failure_modes: |
  <Scenarios where it may be misleading or easily "gamed.">
modality:
  - <e.g. text>

# --- Section 3: Provenance, tooling, and requirements ---
references:            # required
  - >-
    <Citation to peer-reviewed literature or NIST resources, with URL where possible.>
implementation_resources:   # required
  - <URL to software, dataset, or other implementation resource>
common_variants:       # optional
  - <Related variant name>
related_metrics:       # optional
  - <Complementary metric name>
computational_requirements: <optional — e.g. GPU/VRAM/library needs>
usage_rights: <optional — e.g. Apache License 2.0>
```
