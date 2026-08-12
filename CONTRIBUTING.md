# Submission guide

This repository accepts **metrics and measurement methodologies** for AI test,
evaluation, verification, and validation (TEVV), proposed for inclusion in the
[NIST AI Metrology Center](https://airc.nist.gov/metrology/). You submit by opening a
pull request from a fork — no special access needed, and the GitHub web editor is
enough (no local tools required).

## Before you start

- Check the [AI Metrology Center](https://airc.nist.gov/metrology/) to see whether the metric (or a
  close variant) is already listed.
- One metric or measurement method per pull request.
- **Public disclosure:** do not include proprietary or confidential information. Your
  submission file and all review discussion are publicly visible, and posted content
  is considered non-confidential.

## How to submit

1. **Fork** this repository (the "Fork" button, top right).
2. In your fork, **create one YAML file** under `submissions/`, named after your metric
   in lowercase with hyphens — for example `submissions/jailbreak-success-rate.yml`.
   Copy the template from [SUBMISSION_FORMAT.md](SUBMISSION_FORMAT.md) and fill it in.
3. **Open a pull request** from your fork to this repository's `main` branch. The PR
   description is pre-filled with a short checklist.
4. That's it — maintainers are notified automatically when your PR is opened.

Not sure what a finished submission looks like? Two worked examples are kept open as
pull requests — see the
[example submissions](../../pulls?q=is%3Apr+label%3Aexample-submission).

## What to expect after submitting

- **Review typically starts within about two weeks** of your pull request being opened.
  That is when you can expect first contact from a reviewer, not when review concludes —
  discussion may continue for a while after. If two weeks pass with no response, you are
  welcome to leave a comment on your pull request as a reminder.
- **Review happens on the pull request.** Reviewers may ask questions or request
  changes as PR comments. You'll be notified by email — make sure GitHub email
  notifications are enabled on your account.
- **To revise**, edit the file in your fork and push; the pull request updates
  automatically.
- Reviewers may loop in additional subject-matter experts for input.
- The submission format is versioned and may evolve. Your submission is reviewed
  against the `schema_version` your file declares — see
  [SUBMISSION_FORMAT.md](SUBMISSION_FORMAT.md) for the compatibility rules.
- **Acceptance = merge.** When review concludes positively, a maintainer approves and
  merges the pull request. Merged submissions are considered for publication on the
  AI Metrology Center in a subsequent update.
- If a submission isn't a fit, the pull request is closed with an explanation.

## Grounding

Submissions must cite peer-reviewed literature or NIST resources (`references` is
required) and point to usable implementation resources (software, datasets, or other
online resources).
