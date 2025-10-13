# Workflow Templates

This directory contains reusable workflow templates for NASA-PDS repositories.

## Issue Project Automation (Recommended)

The `issue-project-automation.yml` template provides comprehensive project management automation combining:
1. **Auto-add on issue creation**: Automatically adds new issues to specified default projects
2. **Build label automation**: Adds issues to build-specific projects when build labels are added
3. **Sprint planning automation**: Sets iteration to @current when sprint-backlog label is added

### Setup

1. Copy `issue-project-automation.yml` to your repository's `.github/workflows/` directory
2. Edit the `project_numbers` field to match your default project(s):
   - For a single project: `project_numbers: "6"`
   - For multiple projects: `project_numbers: "6,22"`
3. Commit and push the workflow file

---

## Individual Workflow Templates

If you prefer to use specific automation features separately, you can use these individual templates:

### Auto-add Issues to Project

The `auto-add-to-project.yml` template automatically adds newly created issues to specified GitHub Projects.

#### Setup

1. Copy `auto-add-to-project.yml` to your repository's `.github/workflows/` directory
2. Edit the `project_numbers` field to match your project(s):
   - For a single project: `project_numbers: "6"`
   - For multiple projects: `project_numbers: "6,22"`
3. Commit and push the workflow file

#### How it works

- When a new issue is opened, this workflow triggers
- It calls the centralized workflow in the NASA-PDS/.github repository
- The centralized workflow uses the GitHub CLI to add the issue to the specified project(s)

### Label-based Project Management

The `label-to-project.yml` template provides intelligent project management based on issue labels.

See the "Label-based Project Management" section below for full details.

---

## Permissions Setup

**IMPORTANT:** The default `GITHUB_TOKEN` does NOT have permissions to modify organization-level projects. You must create and configure a Personal Access Token (PAT).

### Required Setup:

1. **Create a PAT (Personal Access Token)**:
   - Go to https://github.com/settings/tokens/new (or Settings → Developer settings → Personal access tokens → Tokens (classic))
   - Name it something like "NASA-PDS Project Automation"
   - Select scopes:
     - `repo` (Full control of private repositories)
     - `project` (Full control of projects) - **This is required!**
   - Generate and copy the token

2. **Add PAT as an Organization Secret**:
   - Go to https://github.com/organizations/NASA-PDS/settings/secrets/actions
   - Click "New organization secret"
   - Name: `ORG_PROJECT_PAT`
   - Value: Paste your PAT
   - Repository access: Select "All repositories" or specific repos as needed

3. **Workflow files already configured**:
   - The workflow templates already use `${{ secrets.ORG_PROJECT_PAT }}`
   - No changes needed to the workflow files

---

## Label-Based Automation Features

These features are included in `issue-project-automation.yml` or can be used separately with `label-to-project.yml`.

### Features

#### 1. Build Label Automation
When a build label (e.g., `B16`, `B17`, `B18`) is added to an issue:
- Automatically adds the issue to the organization project with the matching name
- Example: Adding label `B16` → Adds issue to project "B16"

#### 2. Sprint Backlog Automation
When the `sprint-backlog` label is added to an issue:
- Finds all build labels on the issue (e.g., `B16`, `B17`)
- For each build project, sets the issue's iteration to `@current` (the active sprint)
- If the issue isn't in the build project yet, it adds it first

### How it works

**Scenario 1: Adding a build label**
1. User adds label `B17` to an issue
2. Workflow finds the project titled "B17"
3. Issue is added to that project

**Scenario 2: Adding sprint-backlog label**
1. User adds label `sprint-backlog` to an issue that already has `B17` label
2. Workflow finds the "B17" project
3. Issue is added to the project (if not already there)
4. Issue's iteration field is set to the current iteration (@current)

### Usage Tips

- **Build labels**: Must match project titles exactly (case-sensitive)
- **Sprint planning**: Add build label first, then `sprint-backlog` label
- **Multiple builds**: An issue can have multiple build labels (e.g., `B16` and `B17`) and will be added to all matching projects
- **Iteration management**: The workflow automatically detects the current iteration in each project

### Common Build Projects

- B14.0 (Project #4)
- B14.1 (Project #5)
- B15.0 (Project #9)
- B15.1 (Project #14)
- B16 (Project #18)
- B17 (Project #22)

---

## Common Projects

- **Project #6**: EN Portfolio Backlog (main default project)
- **Project #19**: Operations Backlog

---

## Troubleshooting

### Issues not being added to projects:
1. Check the Actions tab in your repository for workflow run logs
2. Verify the project number is correct
3. Check that `ORG_PROJECT_PAT` is configured correctly
4. Verify the NASA-PDS/.github repository workflow is accessible

### Labels not working as expected:
1. Check the Actions tab for workflow run logs
2. Verify the build label matches a project title exactly (case-sensitive)
3. For sprint-backlog: Ensure a build label exists on the issue first
4. Verify the build project has an "Iteration" field configured
5. Check that `ORG_PROJECT_PAT` has appropriate permissions
