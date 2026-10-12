# GitHub Actions Workflows

This directory contains GitHub Actions workflows for the NASA-PDS organization. These workflows automate issue management, project board operations, and sprint planning.

## Organization-wide Workflows

These workflows run in the context of the NASA-PDS organization's `.github` repository and handle org-level automation:

### move-to-next-iteration.yml
**Purpose**: Automatically moves issues forward in sprint iterations

**Type**: Org-wide scheduled workflow

**Trigger**:
- Scheduled: Every Thursday at 07:00 UTC
- Manual: workflow_dispatch

**What it does**:
- Moves all issues from the last sprint iteration to the current sprint
- Operates on NASA-PDS Project #22
- Excludes issues with "Done" status
- Uses the "sprint" iteration field

**Configuration**:
- Organization: `NASA-PDS`
- Project number: `22`
- Requires: `ORG_PROJECT_PAT` secret

---

### stale-prs-slack.yml
**Purpose**: Posts a "Tumbleweeds Report" of stale open PRs to Slack each weekday morning

**Type**: Org-wide scheduled workflow

**Trigger**:
- Scheduled: Weekdays at 15:00 UTC (8am Pacific)
- Manual: workflow_dispatch (with optional `include_dependabot` boolean input)

**What it does**:
1. Extracts ignored repos from `conf/pds-products.yaml`
2. Fetches all open, non-draft PRs in the NASA-PDS org created more than 3 days ago via `fetch-stale-prs.sh`
3. Builds a Slack Block Kit payload via `build-slack-payload.sh` — one compact context block per PR showing title (linked), age, review status, and reviewers
4. POSTs the payload to the configured Slack webhook

**Required secret**: `SLACK_WORKFLOW_WEBHOOK_URL` — Incoming Webhook URL from the **PDS Tumbleweeds App** in the NASA-PDS Slack workspace

**Slack app setup**: See [`.github/scripts/README.md`](../scripts/README.md#slack-app-setup) for how the Slack app was created and how to change the target channel.

**Manual trigger**:
```bash
gh workflow run stale-prs-slack.yml --repo NASA-PDS/.github
```

---

## Reusable Workflow Templates

These workflows are designed to be called from other repositories using `workflow_call`. They provide standardized project management automation that can be adopted by any NASA-PDS repository.

### add-issue-to-project.yml
**Purpose**: Add an issue to one or more GitHub Projects

**Type**: Reusable workflow template (`workflow_call`)

**Inputs**:
- `issue_number`: The issue number to add
- `repository`: Repository in `org/repo` format
- `project_numbers`: Comma-separated project numbers (e.g., "6,22")

**Secrets**:
- `gh_token`: GitHub token with project write permissions (use `ORG_PROJECT_PAT`)

**What it does**:
1. Adds the specified issue to all listed projects (idempotent)
2. Sets the org-level **Product** and **Work Area** fields (Work Area cascades to sub-issues)
3. Processes any build labels (starting with "B") on the issue and adds to corresponding build-specific projects

**Usage example**:
```yaml
jobs:
  add-to-project:
    uses: NASA-PDS/.github/.github/workflows/add-issue-to-project.yml@main
    with:
      issue_number: ${{ github.event.issue.number }}
      repository: ${{ github.repository }}
      project_numbers: "6,22"
    secrets:
      gh_token: ${{ secrets.ORG_PROJECT_PAT }}
```

---

### label-to-project.yml
**Purpose**: Handle label-based project automation

**Type**: Reusable workflow template (`workflow_call`)

**Inputs**:
- `issue_number`: The issue number
- `repository`: Repository in `org/repo` format
- `label_name`: The label that was added or removed
- `action`: Either "labeled" or "unlabeled"

**Secrets**:
- `gh_token`: GitHub token with project write permissions (use `ORG_PROJECT_PAT`)

**What it does**:
- **Build label added** (starting with "B", excluding "bug"): Adds issue to build-specific project; sets org-level Product and Work Area fields; cascades the build label and Work Area to all sub-issues
- **Build label removed**: Removes issue from build project; removes the label from all sub-issues
- **sprint-backlog label added**: Adds issue to the current sprint iteration
- **sprint-backlog label removed**: Clears the sprint field on the issue

**Usage example**:
```yaml
jobs:
  handle-label:
    uses: NASA-PDS/.github/.github/workflows/label-to-project.yml@main
    with:
      issue_number: ${{ github.event.issue.number }}
      repository: ${{ github.repository }}
      label_name: ${{ github.event.label.name }}
      action: ${{ github.event.action }}
    secrets:
      gh_token: ${{ secrets.ORG_PROJECT_PAT }}
```

---

### issue-project-automation.yml
**Purpose**: Complete issue lifecycle automation template

**Type**: Example workflow template (template for repositories to copy)

**Trigger**:
- Issue opened
- Issue labeled
- Issue unlabeled

**What it does**:
This is a **complete example** showing how to use the reusable workflows above. When copied to a repository, it provides:

1. **New issue automation**: Adds newly opened issues to default project(s); sets Product and Work Area fields
2. **Label automation**: Handles build labels (cascade to sub-issues) and sprint-backlog labels
3. **Transfer automation**: Re-evaluates and cascades Work Area when an issue is transferred to a new repo

**How to use in your repository**:
1. Copy this workflow to your repo's `.github/workflows/` directory
2. Update the `project_numbers` on line 18 to match your project(s)
3. Ensure your repository has the `ORG_PROJECT_PAT` secret configured

**Important**: The `GITHUB_TOKEN` does not have permission for organization projects. You must create a Personal Access Token (PAT) with `project` scope and add it as the `ORG_PROJECT_PAT` secret at the organization or repository level.

---

## Required Secrets

All workflows require the `ORG_PROJECT_PAT` secret:

- **Name**: `ORG_PROJECT_PAT`
- **Value**: Personal Access Token from the `pdsen-ci` user
- **Required Scopes**: `project` (read and write access to GitHub Projects)
- **Setup**: The PAT is managed by the `pdsen-ci` service account and configured at the organization level
- **Level**: Set at organization level (accessible to all NASA-PDS repositories)
- **Important**: Private repositories require the secret to be added at both the organization level AND the individual repository level due to GitHub security restrictions

---

## Dependencies

These workflows depend on:

- **Scripts**: `.github/scripts/project-utils.sh` and `.github/scripts/project_automation.py` from the NASA-PDS/.github repository
- **Config**: `conf/pds-products.yaml` — maps repositories to Product and Work Area values
- **External Actions**: `blombard/move-to-next-iteration@master` (for sprint iteration management)

## Running scripts locally

```bash
export GH_TOKEN=$(gh auth token)

# Set Product + Work Area on a single issue (cascades Work Area to sub-issues)
python3 .github/scripts/project_automation.py sync-fields \
  --repository NASA-PDS/validate --issue-number 42 --org NASA-PDS \
  --config conf/pds-products.yaml --set-product-field --set-work-area

# Cascade a build label to all sub-issues of a parent theme
python3 .github/scripts/project_automation.py cascade-label \
  --repository NASA-PDS/systems-engineering --issue-number 165 \
  --label B19 --label-action add

# Backfill Work Area + Product on all issues in one repo (dry-run first)
python3 .github/scripts/project_automation.py backfill-fields \
  --org NASA-PDS --config conf/pds-products.yaml \
  --repo validate --work-area --product --dry-run

# Apply backfill across the whole org
python3 .github/scripts/project_automation.py backfill-fields \
  --org NASA-PDS --config conf/pds-products.yaml --work-area --product
```

---

## Quick Reference

| Workflow | Type | Use Case |
|----------|------|----------|
| `move-to-next-iteration.yml` | Org-wide | Weekly sprint transitions (Thursdays @ 07:00 UTC) |
| `add-issue-to-project.yml` | Reusable | Add issues to projects programmatically |
| `label-to-project.yml` | Reusable | Automate project management based on labels |
| `issue-project-automation.yml` | Template | Complete example to copy to your repo |
