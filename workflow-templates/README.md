# Workflow Templates

This directory contains reusable workflow templates for NASA-PDS repositories.

## Auto-add Issues to Project

The `auto-add-to-project.yml` template automatically adds newly created issues to specified GitHub Projects.

### Setup

1. Copy `auto-add-to-project.yml` to your repository's `.github/workflows/` directory
2. Edit the `project_numbers` field to match your project(s):
   - For a single project: `project_numbers: "6"`
   - For multiple projects: `project_numbers: "6,22"`
3. Commit and push the workflow file

### How it works

- When a new issue is opened, this workflow triggers
- It calls the centralized workflow in the NASA-PDS/.github repository
- The centralized workflow uses the GitHub CLI to add the issue to the specified project(s)

### Project Numbers

Find your project number from the project URL:
- URL format: `https://github.com/orgs/NASA-PDS/projects/6`
- Project number: `6`

### Permissions

**IMPORTANT:** The default `GITHUB_TOKEN` does NOT have permissions to modify organization-level projects. You must create and configure a Personal Access Token (PAT).

#### Required Setup:

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

3. **Update the workflow file**:
   - Change `gh_token: ${{ secrets.GITHUB_TOKEN }}` to `gh_token: ${{ secrets.ORG_PROJECT_PAT }}`

### Common Projects

- Project #6: Main PDS project
- Project #22: (Add description)

### Troubleshooting

If issues are not being added to projects:
1. Check the Actions tab in your repository for workflow run logs
2. Verify the project number is correct
3. Ensure the GITHUB_TOKEN has appropriate permissions
4. Check that the NASA-PDS/.github repository workflow is accessible
