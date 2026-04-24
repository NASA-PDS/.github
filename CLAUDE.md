# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This is the NASA-PDS organization-level `.github` repository. It serves two functions:
1. **Default community health files** — files here (e.g., `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `profile/README.md`) apply org-wide to any NASA-PDS repository that doesn't have its own copy.
2. **Shared GitHub Actions workflows and scripts** — reusable automation for issue/project management, consumed by other NASA-PDS repositories via `uses: NASA-PDS/.github/.github/workflows/<workflow>.yml@main`.

## Key Concepts

- **Build labels** — Labels starting with `"B"` (e.g., `B18`, `B17`) map to a GitHub Projects V2 board for that build sprint. The label `"bug"` is excluded from build-label logic despite starting with `"B"`.
- **sprint-backlog label** — Adding this label puts an issue into the current sprint iteration on the active sprint project. Removing it removes the issue from the sprint.
- **Sprint project** — Currently NASA-PDS Project #25 (used in `move-to-next-iteration.yml`).
- **ORG_PROJECT_PAT** — Required secret for all project-management workflows. Uses a PAT from the `pdsen-ci` service account with `project` scope. `GITHUB_TOKEN` cannot write to org-level projects.

## Workflows Architecture

Three categories of workflows in `.github/workflows/`:

| Workflow | Type | Trigger |
|---|---|---|
| `move-to-next-iteration.yml` | Org-wide scheduled | Fridays 15:00 UTC; manual dispatch |
| `add-issue-to-project.yml` | Reusable (`workflow_call`) | Called by other repos |
| `label-to-project.yml` | Reusable (`workflow_call`) | Called by other repos |
| `issue-project-automation.yml` | Template to copy to repos | Issues opened/labeled/unlabeled |

**Reusable workflows** (called via `uses:`) check out scripts from this repo using sparse checkout of `.github/scripts/`, then execute `project-utils.sh` (bash) or `project_automation.py` (Python).

## Scripts

### `.github/scripts/project_automation.py`
Python CLI using `gh` CLI subprocess calls for GitHub Projects V2 GraphQL API. Main subcommands:
- `add-to-build-project` — finds the build project by label name, adds issue, optionally sets sprint if `sprint-backlog` is already present (`--set-sprint-if-backlog`)
- `add-to-sprint` — adds issue to current sprint iteration on the sprint project
- `remove-from-sprint` — removes issue from the sprint project

### `.github/scripts/project-utils.sh`
Bash utility functions sourced by workflows: `get_issue_id`, `get_project_id_by_number`, `get_project_by_title`, `ensure_issue_in_project`.

## One-off Migration Scripts (Root Level)

- `add_b18_sprint_to_project.py` — Finds all issues with `label:B18 AND label:sprint-backlog` across the org, adds them to the B18 project, and sets the current sprint iteration.
- `add_b17_to_project.py` — Similar migration script for B17.

These are run manually with `python3 <script>.py` (requires `gh` CLI authenticated with appropriate PAT scope).

## Issue Templates (`.github/ISSUE_TEMPLATE/`)

- `-bug_report.yml` / `i-t-bug-report.yml` / `-feature_request.yml` — Standard PDS templates
- `-vulnerability-issue.yml` — Security vulnerability tracking
- `release-theme.yml` — Release planning themes
- `task.yml` — Internal tasks; auto-applies labels `B18,i&t.skip,task` and adds to projects 6 and 25

## PR Template

`.github/pull_request_template.md` requires:
- AI assistance disclosure (required field)
- Test data/report (required)
- Linked issues using `Fixes #N` or `Resolves #N`

## Copilot/AI Review Instructions

`.github/copilot-instructions.md` contains the PR review rubric for Copilot across all NASA-PDS repos. When modifying it, maintain the severity table (`critical` / `high` / `medium` / `low`) and PDS-specific checks (PDS4 schema pinning, Registry/API field names, `search_after` pagination).

## Development Notes

- All scripts require the `gh` CLI authenticated as a user with org project write access.
- Workflows require `ORG_PROJECT_PAT` secret; private repos need it set at both org AND repo level.
- Python scripts use only stdlib + `subprocess` (no pip dependencies).
- When adding new build sprints (e.g., B19), create a new migration script following the pattern in `add_b18_sprint_to_project.py` and update `task.yml` default labels.
