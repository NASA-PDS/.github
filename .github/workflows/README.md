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
2. Processes any build labels (starting with "B") on the issue
3. Automatically adds issue to corresponding build-specific projects

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
- **Build labels** (starting with "B", excluding "bug"): Adds issue to build-specific project
- **sprint-backlog label added**: Adds issue to the current sprint project
- **sprint-backlog label removed**: Removes issue from the sprint project

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

1. **New issue automation**: Automatically adds newly opened issues to default project(s)
2. **Label automation**: Handles build labels and sprint-backlog labels

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
- **External Actions**: `blombard/move-to-next-iteration@master` (for sprint iteration management)

---

## Quick Reference

| Workflow | Type | Use Case |
|----------|------|----------|
| `move-to-next-iteration.yml` | Org-wide | Weekly sprint transitions (Thursdays @ 07:00 UTC) |
| `add-issue-to-project.yml` | Reusable | Add issues to projects programmatically |
| `label-to-project.yml` | Reusable | Automate project management based on labels |
| `issue-project-automation.yml` | Template | Complete example to copy to your repo |
