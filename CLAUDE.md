# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is the NASA-PDS organization-level `.github` repository. It serves two functions:
1. **Default community health files** — files here (e.g., `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `profile/README.md`) apply org-wide to any NASA-PDS repository that doesn't have its own copy.
2. **Shared GitHub Actions workflows and scripts** — reusable automation for issue/project management, consumed by other NASA-PDS repositories via `uses: NASA-PDS/.github/.github/workflows/<workflow>.yml@main`.

## Key Concepts

- **Build labels** — Labels matching `^B\d+$` (e.g., `B18`, `B17`) map to a GitHub Projects V2 board for that build sprint. The label `"bug"` is explicitly excluded from build-label logic despite starting with `"B"`.
- **sprint-backlog label** — Adding this label puts an issue into the current sprint iteration on the active sprint project. Removing it clears the sprint field (does not remove the issue from the project).
- **Sprint project** — Currently NASA-PDS Project #25 (used in `move-to-next-iteration.yml`).
- **ORG_PROJECT_PAT** — Required secret for all project-management workflows. Uses a PAT from the `pdsen-ci` service account with `project` scope. `GITHUB_TOKEN` cannot write to org-level projects.
- **Product field** — A single-select field set on both org-level issues and project items. Populated via `conf/pds-products.yaml`, which maps repo names → product display names.

## Workflows Architecture

| Workflow | Type | Trigger |
|---|---|---|
| `move-to-next-iteration.yml` | Org-wide scheduled | Thursdays 07:00 UTC; manual dispatch |
| `add-issue-to-project.yml` | Reusable (`workflow_call`) | Called by other repos |
| `label-to-project.yml` | Reusable (`workflow_call`) | Called by other repos |
| `issue-project-automation.yml` | Template to copy to repos | Issues opened/labeled/unlabeled |
| `stale-prs-slack.yml` | Org-wide scheduled | Weekday mornings; manual dispatch |

**Reusable workflows** (called via `uses:`) check out scripts from this repo using sparse checkout of `.github/scripts/` and `conf/`, then execute `project-utils.sh` (bash) or `project_automation.py` (Python).

## Scripts

### `.github/scripts/project_automation.py`
Python CLI using `gh` CLI subprocess calls for GitHub Projects V2 GraphQL API. Central class: `GitHubProjectAutomation`. CLI subcommands:
- `add-to-build-project --label BXX` — adds issue to all projects titled `BXX`; `--set-sprint-if-backlog` also sets current sprint when `sprint-backlog` is present; `--config conf/pds-products.yaml` also sets the project-level Product field
- `remove-from-build-project --label BXX` — removes issue from the build project
- `add-to-sprint` — sets iteration to `@current` on all build projects for this issue
- `remove-from-sprint` — clears the sprint/iteration field on all build projects
- `set-product-field --config conf/pds-products.yaml` — sets the Product field at both org level and on any `--project-numbers` items

### `.github/scripts/project-utils.sh`
Bash utility functions sourced by workflows: `get_issue_id`, `get_project_id_by_number`, `get_project_by_title`, `ensure_issue_in_project`, `add_to_sprint`, `remove_from_sprint`.

### `.github/scripts/fetch-stale-prs.sh`
Queries GitHub GraphQL for all open, non-draft PRs in the NASA-PDS org created more than 3 days ago. Writes one JSON object per line to an output file (default `stale_prs.json`). Fetches `reviewRequests` (pending) and `latestReviews` (already reviewed) so both sets of reviewers are available.

### `.github/scripts/build-slack-payload.sh`
Builds a Slack Block Kit JSON payload from stale PR data. Called by `stale-prs-slack.yml`. Accepts `stale_prs.json` and `ignored_repos.json` as positional args; writes payload to stdout. Each PR is rendered as one `context` block (compact, linked title + metadata line). Repos with `ignore: true` in `conf/pds-products.yaml` are excluded. Dependabot PRs are suppressed unless labeled `security` and `INCLUDE_DEPENDABOT=true`.

## Configuration

### `conf/pds-products.yaml`
Maps product names to repositories. Key fields per product:
- `github_project_name` — display name used as the project-level Product field value
- `ignore: true` — repos that should be excluded from org-level tooling (forks, archived, etc.)
- `work_stream` — `core-data-services` | `planetary-data-cloud` | `web-modernization`
- `core_backbone: true` — critical infrastructure; receives scoring bonus

## Root-Level Scripts

- `add_b18_sprint_to_project.py` — Finds all issues with `label:B18 AND label:sprint-backlog`, adds them to the B18 project, sets current sprint.
- `add_b17_to_project.py` — Same pattern for B17.
- `backfill_product_field.py` — Backfills the Product field (org-level and project-level) for all open issues. Supports `--dry-run`, `--force`, `--repo REPO`. Imports `GitHubProjectAutomation` from `.github/scripts/project_automation.py`.

Run with: `python3 <script>.py` (requires `gh` CLI authenticated with project-scope PAT).

## Issue Templates (`.github/ISSUE_TEMPLATE/`)

- `-bug_report.yml` / `i-t-bug-report.yml` / `-feature_request.yml` — Standard PDS templates
- `release-theme.yml` — Release planning themes
- `task.yml` — Internal tasks; auto-applies labels `B18,i&t.skip,task` and adds to projects 6 and 25

## PR Template

`.github/pull_request_template.md` requires AI assistance disclosure, test data/report, and linked issues using `Fixes #N` or `Resolves #N`.

## Copilot/AI Review Instructions

`.github/copilot-instructions.md` contains the PR review rubric for Copilot across all NASA-PDS repos. When modifying it, maintain the severity table (`critical` / `high` / `medium` / `low`) and PDS-specific checks (PDS4 schema pinning, Registry/API field names, `search_after` pagination).

## Local Testing

### Test `project_automation.py` directly
```bash
export GH_TOKEN=$(gh auth token)
python3 .github/scripts/project_automation.py \
  add-to-build-project \
  --repository NASA-PDS/validate \
  --issue-number 42 \
  --org NASA-PDS \
  --label B18 \
  --set-sprint-if-backlog \
  --config conf/pds-products.yaml
```

### Test the Tumbleweeds pipeline locally (see `.github/scripts/README.md` for full steps)
```bash
# Fetch stale PRs (writes stale_prs.json)
GH_TOKEN=$(gh auth token) .github/scripts/fetch-stale-prs.sh stale_prs.json

# Generate ignored repos list (requires PyYAML: pip install pyyaml)
python3 -c "import yaml,json; data=yaml.safe_load(open('conf/pds-products.yaml')); print(json.dumps(['NASA-PDS/'+r for p in data['products'].values() if p.get('ignore') for r in p.get('repositories',[])]))" > ignored_repos.json

# Build and inspect payload
.github/scripts/build-slack-payload.sh stale_prs.json ignored_repos.json | jq .
```

### Trigger workflows manually
```bash
gh workflow run stale-prs-slack.yml --repo NASA-PDS/.github
gh workflow run move-to-next-iteration.yml --repo NASA-PDS/.github
```

## Development Notes

- All scripts require `gh` CLI authenticated as a user with org project write access.
- Workflows require `ORG_PROJECT_PAT` secret; private repos need it set at both org AND repo level.
- Python scripts use only stdlib + `subprocess` (no pip dependencies), except `backfill_product_field.py` which imports from the scripts directory.
- When adding new build sprints (e.g., B19): create a migration script following the pattern in `add_b18_sprint_to_project.py`, and update the default labels in `task.yml`.

## Slack App Setup (Tumbleweeds)

The **PDS Tumbleweeds App** posts the stale PR report via a Slack Incoming Webhook.

### Creating or reconfiguring the app
1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. Name it `PDS Tumbleweeds App`, select the NASA-PDS workspace
3. Under **Features** → **Incoming Webhooks**: toggle on, then **Add New Webhook to Workspace**
4. Select the target channel → **Allow**
5. Copy the generated webhook URL

### Changing the notification channel
Slack Incoming Webhooks are permanently bound to the channel chosen at creation. To post to a different channel:
1. Add a new webhook (step 3–4 above) pointing to the new channel
2. Update the `SLACK_WORKFLOW_WEBHOOK_URL` secret at **github.com/NASA-PDS/.github → Settings → Secrets and variables → Actions**

### Required GitHub secret
| Secret | Value |
|---|---|
| `SLACK_WORKFLOW_WEBHOOK_URL` | Incoming Webhook URL from api.slack.com/apps |
