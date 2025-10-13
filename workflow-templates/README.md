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

The workflow uses `GITHUB_TOKEN` which should have the necessary permissions. If you encounter permission issues, you may need to:

1. Go to your repository Settings → Actions → General
2. Under "Workflow permissions", ensure "Read and write permissions" is selected
3. Check "Allow GitHub Actions to create and approve pull requests" if needed

Or create a Personal Access Token (PAT) or GitHub App token with project write permissions.

### Common Projects

- Project #6: Main PDS project
- Project #22: (Add description)

### Troubleshooting

If issues are not being added to projects:
1. Check the Actions tab in your repository for workflow run logs
2. Verify the project number is correct
3. Ensure the GITHUB_TOKEN has appropriate permissions
4. Check that the NASA-PDS/.github repository workflow is accessible
