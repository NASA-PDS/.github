#!/usr/bin/env python3
"""
GitHub Projects V2 automation utilities.

This script provides automation for managing issues in GitHub Projects V2,
including adding issues to projects and managing sprint iterations.
"""

import subprocess
import json
import sys
import re
import os
from typing import Optional, List, Dict, Any


class GitHubAPIError(Exception):
    """Raised when a GitHub API call fails."""
    pass


class GitHubProjectAutomation:
    """Handles GitHub Projects V2 automation operations."""

    def __init__(self):
        """Initialize the automation handler."""
        pass

    def _run_gh_api(self, args: List[str]) -> str:
        """
        Run gh API command with error handling.

        Args:
            args: Command arguments to pass to gh api

        Returns:
            Command output as string

        Raises:
            GitHubAPIError: If the API call fails
        """
        cmd = ["gh", "api"] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            raise GitHubAPIError(f"API call failed: {error_msg}")

    def get_issue_id(self, repository: str, issue_number: int) -> str:
        """
        Get issue node ID from repository and issue number.

        Args:
            repository: Repository in org/repo format
            issue_number: Issue number

        Returns:
            Issue node ID

        Raises:
            GitHubAPIError: If the API call fails
        """
        try:
            return self._run_gh_api([
                f"repos/{repository}/issues/{issue_number}",
                "--jq", ".node_id"
            ])
        except GitHubAPIError as e:
            raise GitHubAPIError(f"Failed to get issue ID: {e}")

    def get_labels_by_prefix(self, repository: str, issue_number: int, prefix: str) -> List[str]:
        """
        Get all labels starting with a prefix from an issue.

        Args:
            repository: Repository in org/repo format
            issue_number: Issue number
            prefix: Label prefix to filter by

        Returns:
            List of label names

        Raises:
            GitHubAPIError: If the API call fails
        """
        try:
            result = self._run_gh_api([
                f"repos/{repository}/issues/{issue_number}",
                "--jq", f'.labels[].name | select(startswith("{prefix}"))'
            ])
            return [label for label in result.split('\n') if label]
        except GitHubAPIError as e:
            raise GitHubAPIError(f"Failed to get labels: {e}")

    def get_projects_by_title(self, org: str, title: str) -> List[Dict[str, Any]]:
        """
        Get all projects with the given title.

        Args:
            org: Organization name
            title: Project title

        Returns:
            List of dictionaries with 'id', 'number', and 'title' keys

        Raises:
            GitHubAPIError: If the API call fails
        """
        query = """
        query($org: String!) {
            organization(login: $org) {
                projectsV2(first: 100) {
                    nodes {
                        id
                        number
                        title
                    }
                }
            }
        }
        """

        try:
            result = self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"org={org}",
                "--jq", f'[.data.organization.projectsV2.nodes[] | select(.title == "{title}")]'
            ])

            if not result:
                return []

            return json.loads(result)
        except (GitHubAPIError, json.JSONDecodeError) as e:
            raise GitHubAPIError(f"Failed to get projects by title: {e}")

    def get_project_by_title(self, org: str, title: str) -> Optional[Dict[str, Any]]:
        """
        Get first project with the given title (backward-compatible wrapper).

        Returns:
            Dictionary with 'id', 'number', and 'title' keys, or None if not found
        """
        projects = self.get_projects_by_title(org, title)
        return projects[0] if projects else None

    def is_issue_in_project(self, project_id: str, issue_id: str) -> Optional[str]:
        """
        Check if issue is already in project by querying from the issue side.

        Args:
            project_id: Project node ID
            issue_id: Issue node ID

        Returns:
            Item ID if found, None if not in project

        Raises:
            GitHubAPIError: If the API call fails
        """
        query = """
        query($issueId: ID!) {
            node(id: $issueId) {
                ... on Issue {
                    projectItems(first: 20) {
                        nodes {
                            id
                            project { id }
                        }
                    }
                }
            }
        }
        """

        try:
            result = self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"issueId={issue_id}",
                "--jq", f'.data.node.projectItems.nodes[] | select(.project.id == "{project_id}") | .id'
            ])

            return result if result else None
        except GitHubAPIError as e:
            raise GitHubAPIError(f"Failed to check if issue in project: {e}")

    def add_issue_to_project(self, project_id: str, issue_id: str) -> str:
        """
        Add issue to project.

        Args:
            project_id: Project node ID
            issue_id: Issue node ID

        Returns:
            Item ID of the added issue

        Raises:
            GitHubAPIError: If the API call fails
        """
        query = """
        mutation($projectId: ID!, $contentId: ID!) {
            addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
                item {
                    id
                }
            }
        }
        """

        try:
            return self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"projectId={project_id}",
                "-f", f"contentId={issue_id}",
                "--jq", ".data.addProjectV2ItemById.item.id"
            ])
        except GitHubAPIError as e:
            raise GitHubAPIError(f"Failed to add issue to project: {e}")

    def remove_issue_from_project(self, project_id: str, item_id: str) -> None:
        """Remove an item from a project."""
        query = """
        mutation($projectId: ID!, $itemId: ID!) {
            deleteProjectV2Item(input: {projectId: $projectId, itemId: $itemId}) {
                deletedItemId
            }
        }
        """
        try:
            self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"projectId={project_id}",
                "-f", f"itemId={item_id}"
            ])
        except GitHubAPIError as e:
            raise GitHubAPIError(f"Failed to remove issue from project: {e}")

    def ensure_issue_in_project(self, project_id: str, issue_id: str) -> str:
        """
        Get or add issue to project (idempotent).

        Args:
            project_id: Project node ID
            issue_id: Issue node ID

        Returns:
            Item ID

        Raises:
            GitHubAPIError: If the operation fails
        """
        item_id = self.is_issue_in_project(project_id, issue_id)
        if item_id:
            return item_id
        return self.add_issue_to_project(project_id, issue_id)

    def get_iteration_field(self, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Get iteration field data from project.

        Args:
            project_id: Project node ID

        Returns:
            Dictionary with field id and configuration, or None if not found

        Raises:
            GitHubAPIError: If the API call fails
        """
        query = """
        query($projectId: ID!) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    fields(first: 20) {
                        nodes {
                            ... on ProjectV2IterationField {
                                id
                                name
                                configuration {
                                    iterations {
                                        id
                                        title
                                        startDate
                                    }
                                    completedIterations {
                                        id
                                        title
                                        startDate
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        try:
            result = self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"projectId={project_id}",
                "--jq", '.data.node.fields.nodes[] | select(.name == "Iteration" or .name == "Sprint")'
            ])

            if not result:
                return None

            return json.loads(result)
        except (GitHubAPIError, json.JSONDecodeError) as e:
            raise GitHubAPIError(f"Failed to get iteration field: {e}")

    def set_iteration_to_current(self, project_id: str, item_id: str) -> bool:
        """
        Set iteration field to current iteration.

        Args:
            project_id: Project node ID
            item_id: Project item ID

        Returns:
            True if successful, False otherwise
        """
        try:
            field_data = self.get_iteration_field(project_id)

            if not field_data:
                print("⚠️  No Iteration field found", file=sys.stderr)
                return False

            field_id = field_data['id']
            iterations = field_data.get('configuration', {}).get('iterations', [])

            if not iterations:
                print("⚠️  No current iteration found", file=sys.stderr)
                return False

            current_iteration_id = iterations[0]['id']

            query = """
            mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $iterationId: String!) {
                updateProjectV2ItemFieldValue(input: {
                    projectId: $projectId
                    itemId: $itemId
                    fieldId: $fieldId
                    value: {
                        iterationId: $iterationId
                    }
                }) {
                    projectV2Item {
                        id
                    }
                }
            }
            """

            self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"projectId={project_id}",
                "-f", f"itemId={item_id}",
                "-f", f"fieldId={field_id}",
                "-f", f"iterationId={current_iteration_id}"
            ])

            return True

        except (GitHubAPIError, KeyError) as e:
            print(f"⚠️  Failed to set iteration: {e}", file=sys.stderr)
            return False

    def clear_iteration(self, project_id: str, item_id: str) -> bool:
        """
        Clear iteration field (set to null).

        Args:
            project_id: Project node ID
            item_id: Project item ID

        Returns:
            True if successful, False otherwise
        """
        try:
            field_data = self.get_iteration_field(project_id)

            if not field_data:
                print("⚠️  No Sprint/Iteration field found", file=sys.stderr)
                return False

            field_id = field_data['id']

            query = """
            mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!) {
                clearProjectV2ItemFieldValue(input: {
                    projectId: $projectId
                    itemId: $itemId
                    fieldId: $fieldId
                }) {
                    projectV2Item {
                        id
                    }
                }
            }
            """

            self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"projectId={project_id}",
                "-f", f"itemId={item_id}",
                "-f", f"fieldId={field_id}"
            ])

            return True

        except (GitHubAPIError, KeyError) as e:
            print(f"⚠️  Failed to clear iteration: {e}", file=sys.stderr)
            return False

    def process_sprint_for_build_labels(
        self,
        repository: str,
        issue_number: int,
        org: str,
        action: str
    ) -> int:
        """
        Process sprint automation for all build labels on an issue.

        Args:
            repository: Repository in org/repo format
            issue_number: Issue number
            org: Organization name
            action: Either 'add' or 'remove'

        Returns:
            Number of projects successfully updated
        """
        action_verb = "Adding to" if action == "add" else "Removing from"
        print(f"{action_verb} sprint for issue #{issue_number}")

        try:
            # Get issue node ID
            issue_id = self.get_issue_id(repository, issue_number)
            print(f"Issue node ID: {issue_id}")

            # Find all build labels on this issue
            build_labels = self.get_labels_by_prefix(repository, issue_number, "B")

            if not build_labels:
                if action == "add":
                    print("⚠️  No build label found on issue")
                    print("ℹ️  Please add a build label (e.g., B16, B17) before adding sprint-backlog")
                else:
                    print("ℹ️  No build labels found on issue - nothing to clear")
                return 0

            print(f"Found build labels: {', '.join(build_labels)}")
            print()

            # Process each build label
            success_count = 0
            for build_label in build_labels:
                print(f"Processing {action} for build: {build_label}")

                # Find all projects with matching title
                projects = self.get_projects_by_title(org, build_label)

                if not projects:
                    print(f"⚠️  No project found for build '{build_label}' - skipping")
                    print()
                    continue

                print(f"Found {len(projects)} project(s) for '{build_label}'")

                for project_data in projects:
                    project_id = project_data['id']
                    project_number = project_data['number']

                    print(f"Processing project #{project_number}: {build_label}")

                    if action == "add":
                        # Ensure issue is in project
                        item_id = self.ensure_issue_in_project(project_id, issue_id)

                        if not item_id:
                            print(f"❌ Failed to add issue to project #{project_number}")
                            continue

                        print(f"✅ Issue in project (item: {item_id})")

                        # Set iteration to current
                        if self.set_iteration_to_current(project_id, item_id):
                            print(f"✅ Set iteration to @current in project #{project_number}")
                            success_count += 1
                        else:
                            print(f"❌ Failed to set iteration in project #{project_number}")

                    else:  # remove
                        # Check if issue is in project
                        item_id = self.is_issue_in_project(project_id, issue_id)

                        if not item_id:
                            print(f"ℹ️  Issue not in project #{project_number} - nothing to clear")
                            success_count += 1  # Count as success since there's nothing to remove
                            continue

                        print(f"✅ Issue in project (item: {item_id})")

                        # Clear the sprint/iteration field
                        if self.clear_iteration(project_id, item_id):
                            print(f"✅ Cleared sprint in project #{project_number}")
                            success_count += 1
                        else:
                            print(f"❌ Failed to clear sprint in project #{project_number}")

                print()

            if success_count > 0:
                print(f"✅ Sprint {action} complete ({success_count} project(s) updated)")
            else:
                print("⚠️  No projects were updated")

            return success_count

        except GitHubAPIError as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(1)


    def issue_has_label(self, repository: str, issue_number: int, label: str) -> bool:
        """Check if an issue has a specific label."""
        try:
            result = self._run_gh_api([
                f"repos/{repository}/issues/{issue_number}",
                "--jq", f'.labels[].name | select(. == "{label}")'
            ])
            return bool(result.strip())
        except GitHubAPIError:
            return False

    def add_issue_to_build_project(
        self,
        repository: str,
        issue_number: int,
        org: str,
        label: str,
        set_sprint_if_backlog: bool = False
    ) -> bool:
        """
        Add an issue to all build projects matching the label title.

        Args:
            repository: Repository in org/repo format
            issue_number: Issue number
            org: Organization name
            label: Build label (e.g., "B16")
            set_sprint_if_backlog: If True, also set current sprint when sprint-backlog label is present

        Returns:
            True if successful, False otherwise
        """
        print(f"Processing build label: {label}")

        # Validate build label format (B followed by digits)
        if not re.match(r'^B\d+$', label):
            print(f"ℹ️  Label '{label}' does not match build label pattern (B followed by digits) - skipping")
            return True  # Not an error, just not a build label

        repo_name = repository.split('/')[-1]

        try:
            # Get issue node ID
            issue_id = self.get_issue_id(repository, issue_number)
            print(f"Issue node ID: {issue_id}")

            # Find all projects with matching title
            projects = self.get_projects_by_title(org, label)

            if not projects:
                print(f"ℹ️  No project found with title '{label}' - skipping (this is okay, the project may not exist yet)")
                return True  # Not an error, just no matching project

            print(f"Found {len(projects)} project(s) for '{label}'")

            # Check if sprint should be set
            has_sprint_backlog = set_sprint_if_backlog and self.issue_has_label(repository, issue_number, "sprint-backlog")
            if set_sprint_if_backlog:
                print(f"sprint-backlog label present: {has_sprint_backlog}")

            all_success = True
            for project_data in projects:
                project_id = project_data['id']
                project_number = project_data['number']

                print(f"Found project #{project_number}: {label}")
                print(f"Project ID: {project_id}")

                # Add issue to project (idempotent)
                item_id = self.ensure_issue_in_project(project_id, issue_id)

                if not item_id:
                    print(f"❌ Failed to add to project #{project_number}")
                    all_success = False
                    continue

                print(f"✅ Issue in project #{project_number} (item: {item_id})")

                # Set sprint if sprint-backlog is present
                if has_sprint_backlog:
                    if self.set_iteration_to_current(project_id, item_id):
                        print(f"✅ Set iteration to @current in project #{project_number}")
                    else:
                        print(f"⚠️  Failed to set iteration in project #{project_number}")

            return all_success

        except GitHubAPIError as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(1)

    def remove_issue_from_build_project(
        self,
        repository: str,
        issue_number: int,
        org: str,
        label: str
    ) -> bool:
        """Remove an issue from all build projects matching the label title.

        Args:
            repository: Repository in org/repo format
            issue_number: Issue number
            org: Organization name
            label: Build label being removed (e.g., "B18")

        Returns:
            True if successful, False otherwise
        """
        print(f"Removing issue from build project for label: {label}")

        if not re.match(r'^B\d+$', label):
            print(f"ℹ️  Label '{label}' does not match build label pattern — skipping")
            return True

        try:
            issue_id = self.get_issue_id(repository, issue_number)
            print(f"Issue node ID: {issue_id}")

            projects = self.get_projects_by_title(org, label)

            if not projects:
                print(f"ℹ️  No project found with title '{label}' — nothing to remove from")
                return True

            all_success = True
            for project_data in projects:
                project_id = project_data['id']
                project_number = project_data['number']

                item_id = self.is_issue_in_project(project_id, issue_id)
                if not item_id:
                    print(f"ℹ️  Issue not in project #{project_number} — nothing to remove")
                    continue

                self.remove_issue_from_project(project_id, item_id)
                print(f"✅ Removed issue from project #{project_number} ({label})")

            return all_success

        except GitHubAPIError as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(1)

    def get_project_id_by_number(self, org: str, project_number: int) -> Optional[str]:
        """Get project node ID from org and project number."""
        query = """
        query($org: String!, $number: Int!) {
            organization(login: $org) {
                projectV2(number: $number) {
                    id
                }
            }
        }
        """
        try:
            result = self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"org={org}",
                "-F", f"number={project_number}",
                "--jq", ".data.organization.projectV2.id"
            ])
            return result if result else None
        except GitHubAPIError as e:
            raise GitHubAPIError(f"Failed to get project by number: {e}")

    def get_project_single_select_field(self, project_id: str, field_name: str) -> Optional[Dict[str, Any]]:
        """Get a single-select field definition (id + options) from a project."""
        query = """
        query($projectId: ID!) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    fields(first: 50) {
                        nodes {
                            ... on ProjectV2SingleSelectField {
                                id
                                name
                                options {
                                    id
                                    name
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        try:
            result = self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"projectId={project_id}",
                "--jq", f'.data.node.fields.nodes[] | select(.name == "{field_name}")'
            ])
            return json.loads(result) if result else None
        except (GitHubAPIError, json.JSONDecodeError) as e:
            raise GitHubAPIError(f"Failed to get project single-select field '{field_name}': {e}")

    def set_project_single_select_field(
        self, project_id: str, item_id: str, field_id: str, option_id: str
    ) -> None:
        """Set a single-select field value on a project item."""
        query = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
            updateProjectV2ItemFieldValue(input: {
                projectId: $projectId
                itemId: $itemId
                fieldId: $fieldId
                value: { singleSelectOptionId: $optionId }
            }) {
                projectV2Item { id }
            }
        }
        """
        try:
            self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"projectId={project_id}",
                "-f", f"itemId={item_id}",
                "-f", f"fieldId={field_id}",
                "-f", f"optionId={option_id}"
            ])
        except GitHubAPIError as e:
            raise GitHubAPIError(f"Failed to set project single-select field: {e}")

    def get_org_issue_field(self, org: str, field_name: str) -> Optional[Dict[str, Any]]:
        """Get an org-level issue field by name, returning its id and options."""
        try:
            result = self._run_gh_api([
                f"orgs/{org}/issue-fields",
                "--jq", f'.[] | select(.name == "{field_name}")'
            ])
            return json.loads(result) if result else None
        except (GitHubAPIError, json.JSONDecodeError) as e:
            raise GitHubAPIError(f"Failed to get org issue field '{field_name}': {e}")

    def set_org_issue_field_value(
        self, repository: str, issue_number: int, field_id: int, value: str
    ) -> None:
        """Set a single org-level issue field value via REST PUT."""
        self.set_org_issue_field_values(repository, issue_number, [(field_id, value)])

    def set_org_issue_field_values(
        self, repository: str, issue_number: int, fields: List[tuple]
    ) -> None:
        """Merge field updates into the issue's existing org field values and PUT.

        The REST PUT endpoint replaces ALL org field values, so we read the current
        state first and merge our updates on top before writing.

        Args:
            fields: List of (field_id, value) tuples to set or overwrite.
        """
        # Read existing field values so unrelated fields are preserved on the PUT.
        # The PUT endpoint replaces ALL values, so we must round-trip every set field.
        #
        # PUT value format by data_type:
        #   single_select  -> option name string  (from .single_select_option.name)
        #   multi_select   -> list of option name strings (from .multi_select_options[].name)
        #   text           -> string              (from .value directly)
        #   number         -> number              (from .value directly)
        #   date           -> ISO 8601 string     (from .value directly)
        existing: Dict[int, Any] = {}
        try:
            raw_json = self._run_gh_api([
                f"repos/{repository}/issues/{issue_number}/issue-field-values"
            ])
            for entry in (json.loads(raw_json) if raw_json else []):
                fid = entry['issue_field_id']
                dtype = entry.get('data_type')
                if dtype == 'single_select':
                    opt = entry.get('single_select_option')
                    if opt:
                        existing[fid] = opt['name']
                elif dtype == 'multi_select':
                    opts = entry.get('multi_select_options', [])
                    if opts:
                        existing[fid] = [o['name'] for o in opts]
                else:
                    # text, number, date — .value is the correct PUT representation
                    if entry.get('value') is not None:
                        existing[fid] = entry['value']
        except (GitHubAPIError, json.JSONDecodeError):
            pass

        # Overlay our updates
        for fid, val in fields:
            existing[fid] = val

        body = json.dumps({"issue_field_values": [
            {"field_id": fid, "value": val} for fid, val in existing.items()
        ]})
        cmd = ["gh", "api", "-X", "PUT",
               f"repos/{repository}/issues/{issue_number}/issue-field-values",
               "--input", "-"]
        try:
            subprocess.run(cmd, input=body, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            raise GitHubAPIError(f"Failed to set org issue field values: {error_msg}")

    @staticmethod
    def _load_products_config(config_path: str) -> Dict[str, Any]:
        """Parse pds-products.yaml without external dependencies.

        Returns a dict keyed by product name with 'repositories', 'github_project_name',
        'work_area', and 'ignore' entries.
        """
        products: Dict[str, Any] = {}
        current_product: Optional[str] = None
        in_products_section = False
        in_repos = False

        with open(config_path) as f:
            for raw_line in f:
                line = raw_line.rstrip('\n')
                stripped = line.lstrip()

                if not stripped or stripped.startswith('#'):
                    continue

                indent = len(line) - len(stripped)

                if line == 'products:':
                    in_products_section = True
                    current_product = None
                    in_repos = False
                    continue

                if not in_products_section:
                    continue

                # Any top-level key signals the end of the products block
                if indent == 0:
                    break

                # Product key: 2-space indent, ends with ':'
                if indent == 2 and stripped.endswith(':') and not stripped.startswith('-'):
                    current_product = stripped[:-1]
                    products[current_product] = {'repositories': []}
                    in_repos = False
                    continue

                if current_product is None:
                    continue

                # Product properties: 4-space indent
                if indent == 4:
                    in_repos = False
                    if stripped.startswith('repositories:'):
                        in_repos = True
                    elif stripped.startswith('github_project_name:'):
                        val = stripped.split(':', 1)[1].strip().strip('"\'')
                        products[current_product]['github_project_name'] = val
                    elif stripped.startswith('work_area:'):
                        val = stripped.split(':', 1)[1].strip().strip('"\'')
                        products[current_product]['work_area'] = val
                    elif stripped.startswith('ignore:'):
                        val = stripped.split(':', 1)[1].strip()
                        products[current_product]['ignore'] = val == 'true'
                    continue

                # Repository items: 6-space indent
                if indent == 6 and in_repos and stripped.startswith('- '):
                    repo = stripped[2:].strip().strip('"\'')
                    products[current_product]['repositories'].append(repo)

        return products

    @staticmethod
    def _find_product_for_repo(products: Dict[str, Any], repo_name: str) -> Optional[str]:
        """Return the display name (github_project_name or key) for a repo, or None."""
        for product_key, info in products.items():
            if info.get('ignore'):
                continue
            if repo_name in info.get('repositories', []):
                return info.get('github_project_name') or product_key
        return None

    @staticmethod
    def _find_work_area_for_repo(products: Dict[str, Any], repo_name: str) -> Optional[str]:
        """Return the work_area value for a repo, or None."""
        for info in products.values():
            if info.get('ignore'):
                continue
            if repo_name in info.get('repositories', []):
                return info.get('work_area')
        return None

    def get_issue_parent(self, issue_id: str) -> Optional[Dict[str, Any]]:
        """Return the parent issue's id, number, and repository, or None if no parent."""
        query = """
        query($issueId: ID!) {
            node(id: $issueId) {
                ... on Issue {
                    parent {
                        id
                        number
                        repository {
                            nameWithOwner
                            name
                        }
                    }
                }
            }
        }
        """
        try:
            result = self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"issueId={issue_id}",
                "--jq", ".data.node.parent"
            ])
            if not result or result == "null":
                return None
            return json.loads(result)
        except (GitHubAPIError, json.JSONDecodeError):
            return None

    def get_issue_current_work_area(self, issue_id: str, org: str) -> Optional[str]:
        """Return the current Work Area field value on an issue, or None if unset."""
        query = """
        query($issueId: ID!) {
            node(id: $issueId) {
                ... on Issue {
                    issueFieldValues(first: 20) {
                        nodes {
                            ... on IssueFieldSingleSelectValue {
                                field { ... on IssueFieldSingleSelect { name } }
                                optionId
                                name
                            }
                        }
                    }
                }
            }
        }
        """
        try:
            result = self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"issueId={issue_id}",
                "--jq", '.data.node.issueFieldValues.nodes[] | select(.field.name == "Work Area") | .name'
            ])
            return result if result else None
        except GitHubAPIError:
            return None

    def get_issue_sub_issues(self, issue_id: str) -> List[Dict[str, Any]]:
        """Return list of direct sub-issues (id, number, repository) for an issue."""
        query = """
        query($issueId: ID!) {
            node(id: $issueId) {
                ... on Issue {
                    subIssues(first: 100) {
                        nodes {
                            id
                            number
                            repository {
                                nameWithOwner
                                name
                            }
                        }
                    }
                }
            }
        }
        """
        try:
            result = self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"issueId={issue_id}",
                "--jq", ".data.node.subIssues.nodes"
            ])
            if not result or result == "null":
                return []
            return json.loads(result)
        except (GitHubAPIError, json.JSONDecodeError):
            return []

    def resolve_work_area(
        self,
        repository: str,
        issue_number: int,
        issue_id: str,
        config_path: str
    ) -> Optional[str]:
        """
        Determine the correct work area for an issue.

        Walks up the parent chain until a root issue is found (no parent),
        then returns that root issue's repo-based work area. This ensures all
        issues in a hierarchy share the theme/root owner's work area.
        """
        products = self._load_products_config(config_path)

        current_id = issue_id
        current_repo = repository

        # Walk up to the root of the parent chain
        while True:
            parent = self.get_issue_parent(current_id)
            if not parent:
                break
            current_id = parent['id']
            current_repo = parent['repository']['nameWithOwner']

        repo_name = current_repo.split('/')[-1]
        return self._find_work_area_for_repo(products, repo_name)

    def set_work_area(
        self,
        repository: str,
        issue_number: int,
        work_area_name: str,
        org: str
    ) -> bool:
        """Set the org-level Work Area field on an issue."""
        try:
            field_data = self.get_org_issue_field(org, "Work Area")
            if not field_data:
                print("ℹ️  No 'Work Area' org issue field found — skipping", file=sys.stderr)
                return True

            field_id = field_data['id']
            options = field_data.get('options', [])
            valid_names = [o['name'] for o in options]
            if work_area_name not in valid_names:
                print(
                    f"⚠️  '{work_area_name}' is not a valid Work Area option. "
                    f"Available: {valid_names}",
                    file=sys.stderr
                )
                return False

            self.set_org_issue_field_value(repository, issue_number, field_id, work_area_name)
            print(f"✅ Set Work Area to '{work_area_name}' on {repository}#{issue_number}")
            return True

        except GitHubAPIError as e:
            print(f"❌ Work Area field: {e}", file=sys.stderr)
            return False

    def set_work_area_field(
        self,
        repository: str,
        issue_number: int,
        org: str,
        config_path: str,
        cascade: bool = True
    ) -> bool:
        """
        Set the Work Area org field on an issue and optionally cascade to all sub-issues.

        The work area is resolved by walking to the root of the parent chain and using
        that root issue's repo-based work area from the config.

        Args:
            repository: Repository in org/repo format
            issue_number: Issue number
            org: Organization name
            config_path: Path to pds-products.yaml
            cascade: If True, also set Work Area on all direct sub-issues recursively

        Returns True on success or benign skip, False on hard failure.
        """
        if not os.path.exists(config_path):
            print(f"⚠️  Products config not found: {config_path}", file=sys.stderr)
            return False

        try:
            issue_id = self.get_issue_id(repository, issue_number)
        except GitHubAPIError as e:
            print(f"❌ Could not get issue node ID: {e}", file=sys.stderr)
            return False

        work_area = self.resolve_work_area(repository, issue_number, issue_id, config_path)
        if not work_area:
            print(f"ℹ️  No work_area mapping for '{repository.split('/')[-1]}' — skipping")
            return True

        print(f"Resolved work area: '{work_area}' for {repository}#{issue_number}")
        success = self.set_work_area(repository, issue_number, work_area, org)

        if cascade and success:
            self._cascade_work_area_to_sub_issues(issue_id, work_area, org, config_path)

        return success

    def sync_fields(
        self,
        repository: str,
        issue_number: int,
        org: str,
        config_path: str,
        set_product: bool = False,
        set_work_area: bool = False,
        cascade: bool = True,
        field_name: str = "Product"
    ) -> bool:
        """Set Product and/or Work Area org fields in a single batched PUT.

        Both fields are written atomically so neither overwrites the other.
        Work Area cascade to sub-issues runs after the PUT succeeds.
        """
        if not os.path.exists(config_path):
            print(f"⚠️  Products config not found: {config_path}", file=sys.stderr)
            return False

        products = self._load_products_config(config_path)
        repo_name = repository.split('/')[-1]

        try:
            issue_id = self.get_issue_id(repository, issue_number)
        except GitHubAPIError as e:
            print(f"❌ Could not get issue node ID: {e}", file=sys.stderr)
            return False

        # (field_id, value, display_name) — batched into a single PUT
        field_writes: List[tuple] = []
        work_area_value: Optional[str] = None

        if set_product:
            product_name = self._find_product_for_repo(products, repo_name)
            if not product_name:
                print(f"ℹ️  No product mapping for '{repo_name}' — skipping '{field_name}' field")
            else:
                print(f"Repo '{repo_name}' → product '{product_name}'")
                try:
                    field_data = self.get_org_issue_field(org, field_name)
                    if not field_data:
                        print(f"ℹ️  No '{field_name}' org issue field found — skipping")
                    else:
                        options = field_data.get('options', [])
                        if options and product_name not in [o['name'] for o in options]:
                            print(
                                f"⚠️  '{product_name}' is not a valid option for org '{field_name}'. "
                                f"Available: {[o['name'] for o in options]}",
                                file=sys.stderr
                            )
                            return False
                        field_writes.append((field_data['id'], product_name, field_name))
                except GitHubAPIError as e:
                    print(f"❌ Could not resolve '{field_name}' field: {e}", file=sys.stderr)
                    return False

        if set_work_area:
            work_area_value = self.resolve_work_area(repository, issue_number, issue_id, config_path)
            if not work_area_value:
                print(f"ℹ️  No work_area mapping for '{repo_name}' — skipping Work Area field")
            else:
                print(f"Resolved work area: '{work_area_value}' for {repository}#{issue_number}")
                try:
                    wa_field = self.get_org_issue_field(org, "Work Area")
                    if not wa_field:
                        print("ℹ️  No 'Work Area' org issue field found — skipping")
                        work_area_value = None
                    else:
                        options = wa_field.get('options', [])
                        if options and work_area_value not in [o['name'] for o in options]:
                            print(
                                f"⚠️  '{work_area_value}' is not a valid Work Area option. "
                                f"Available: {[o['name'] for o in options]}",
                                file=sys.stderr
                            )
                            return False
                        field_writes.append((wa_field['id'], work_area_value, "Work Area"))
                except GitHubAPIError as e:
                    print(f"❌ Could not resolve 'Work Area' field: {e}", file=sys.stderr)
                    return False

        if not field_writes:
            return True

        try:
            self.set_org_issue_field_values(
                repository, issue_number, [(fid, val) for fid, val, _ in field_writes]
            )
            for _, val, label in field_writes:
                print(f"✅ Set org '{label}' to '{val}' on {repository}#{issue_number}")
        except GitHubAPIError as e:
            print(f"❌ {e}", file=sys.stderr)
            return False

        if cascade and work_area_value:
            self._cascade_work_area_to_sub_issues(issue_id, work_area_value, org, config_path)

        return True

    def _cascade_work_area_to_sub_issues(
        self,
        parent_issue_id: str,
        work_area: str,
        org: str,
        config_path: str
    ) -> None:
        """Recursively set work_area on all sub-issues of parent_issue_id."""
        sub_issues = self.get_issue_sub_issues(parent_issue_id)
        for sub in sub_issues:
            repo = sub['repository']['nameWithOwner']
            number = sub['number']
            sub_id = sub['id']
            print(f"  Cascading Work Area '{work_area}' to sub-issue {repo}#{number}")
            try:
                self.set_work_area(repo, number, work_area, org)
                self._cascade_work_area_to_sub_issues(sub_id, work_area, org, config_path)
            except GitHubAPIError as e:
                print(f"  ⚠️  Could not set sub-issue {repo}#{number}: {e}", file=sys.stderr)

    def cascade_label_to_sub_issues(
        self,
        repository: str,
        issue_number: int,
        label: str,
        action: str = "add"
    ) -> int:
        """Recursively add or remove a label on all sub-issues of an issue.

        Args:
            repository: Repository in org/repo format
            issue_number: Issue number
            label: Label name to add or remove
            action: "add" or "remove"

        Returns:
            Number of sub-issues updated
        """
        if not re.match(r'^B\d+$', label):
            print(f"ℹ️  '{label}' is not a build label — skipping cascade")
            return 0

        try:
            issue_id = self.get_issue_id(repository, issue_number)
        except GitHubAPIError as e:
            print(f"❌ Could not get issue node ID: {e}", file=sys.stderr)
            return 0

        return self._cascade_label(issue_id, label, action)

    def _cascade_label(
        self,
        parent_issue_id: str,
        label: str,
        action: str
    ) -> int:
        """Recursive implementation of label cascade."""
        sub_issues = self.get_issue_sub_issues(parent_issue_id)
        updated = 0
        for sub in sub_issues:
            repo = sub['repository']['nameWithOwner']
            number = sub['number']
            sub_id = sub['id']
            try:
                if action == "add":
                    self._run_gh_api([
                        f"repos/{repo}/issues/{number}/labels",
                        "-X", "POST",
                        "-f", f"labels[]={label}"
                    ])
                    print(f"  ✅ Added '{label}' to {repo}#{number}")
                else:
                    self._run_gh_api([
                        f"repos/{repo}/issues/{number}/labels/{label}",
                        "-X", "DELETE"
                    ])
                    print(f"  ✅ Removed '{label}' from {repo}#{number}")
                updated += 1
            except GitHubAPIError as e:
                # 404 on DELETE means label wasn't present — not an error
                if action == "remove" and "404" in str(e):
                    print(f"  ℹ️  '{label}' not on {repo}#{number} — skipping")
                else:
                    print(f"  ⚠️  Could not {action} label on {repo}#{number}: {e}", file=sys.stderr)
            updated += self._cascade_label(sub_id, label, action)
        return updated

    def _get_current_org_field_values(
        self, repository: str, issue_number: int, org: str
    ) -> Dict[str, Optional[str]]:
        """Return {field_name: value} for Work Area and Product on an issue, or None if unset."""
        query = """
        query($issueId: ID!) {
            node(id: $issueId) {
                ... on Issue {
                    issueFieldValues(first: 20) {
                        nodes {
                            ... on IssueFieldSingleSelectValue {
                                field { ... on IssueFieldSingleSelect { name } }
                                name
                            }
                        }
                    }
                }
            }
        }
        """
        result: Dict[str, Optional[str]] = {"Work Area": None, "Product": None}
        try:
            issue_id = self.get_issue_id(repository, issue_number)
            raw = self._run_gh_api([
                "graphql",
                "-f", f"query={query}",
                "-f", f"issueId={issue_id}",
                "--jq", ".data.node.issueFieldValues.nodes"
            ])
            for node in (json.loads(raw) if raw else []):
                fname = (node.get('field') or {}).get('name')
                if fname in result:
                    result[fname] = node.get('name')
        except (GitHubAPIError, json.JSONDecodeError):
            pass
        return result

    def backfill_fields(
        self,
        org: str,
        config_path: str,
        backfill_work_area: bool = True,
        backfill_product: bool = False,
        repo_filter: Optional[str] = None,
        dry_run: bool = False,
        force: bool = False
    ) -> int:
        """Backfill Work Area and/or Product org fields on all open issues missing them.

        Args:
            org: Organization name
            config_path: Path to pds-products.yaml
            backfill_work_area: Set Work Area field
            backfill_product: Set Product field
            repo_filter: If set, only process this repo name
            dry_run: Print what would be done without making changes
            force: Re-set fields even if already set

        Returns:
            Number of issues updated (or that would be updated in dry-run mode)
        """
        if not backfill_work_area and not backfill_product:
            print("❌ at least one of --work-area or --product is required", file=sys.stderr)
            return 0

        if not os.path.exists(config_path):
            print(f"⚠️  Products config not found: {config_path}", file=sys.stderr)
            return 0

        products = self._load_products_config(config_path)

        # Pre-fetch org field IDs once
        wa_field = self.get_org_issue_field(org, "Work Area") if backfill_work_area else None
        prod_field = self.get_org_issue_field(org, "Product") if backfill_product else None

        updated = 0

        for product_key, info in products.items():
            if info.get('ignore'):
                continue

            work_area = info.get('work_area') if backfill_work_area else None
            product_name = (info.get('github_project_name') or product_key) if backfill_product else None

            if not work_area and not product_name:
                continue

            for repo_name in info.get('repositories', []):
                if repo_filter and repo_name != repo_filter:
                    continue

                repository = f"{org}/{repo_name}"
                fields_desc = ", ".join(filter(None, [
                    f"work_area={work_area}" if work_area else None,
                    f"product={product_name}" if product_name else None,
                ]))
                print(f"\nProcessing {repository} ({fields_desc})")

                try:
                    issues_json = self._run_gh_api([
                        f"repos/{repository}/issues?state=open&per_page=100",
                        "--jq", "[.[] | {number: .number, node_id: .node_id, title: .title}]"
                    ])
                except GitHubAPIError as e:
                    print(f"  ⚠️  Could not list issues for {repository}: {e}", file=sys.stderr)
                    continue

                if not issues_json:
                    continue

                try:
                    issues = json.loads(issues_json)
                except json.JSONDecodeError:
                    continue

                for issue in issues:
                    number = issue['number']

                    # Determine which fields need writing for this issue
                    if not force:
                        current = self._get_current_org_field_values(repository, number, org)
                        fields_to_write = []
                        if work_area and wa_field and not current["Work Area"]:
                            fields_to_write.append((wa_field['id'], work_area, "Work Area"))
                        if product_name and prod_field and not current["Product"]:
                            fields_to_write.append((prod_field['id'], product_name, "Product"))
                        if not fields_to_write:
                            already = ", ".join(
                                f"{k}='{v}'" for k, v in current.items() if v
                            )
                            print(f"  ℹ️  #{number} already has {already} — skipping")
                            continue
                    else:
                        fields_to_write = []
                        if work_area and wa_field:
                            fields_to_write.append((wa_field['id'], work_area, "Work Area"))
                        if product_name and prod_field:
                            fields_to_write.append((prod_field['id'], product_name, "Product"))

                    labels_desc = ", ".join(f"{n}='{v}'" for _, v, n in fields_to_write)
                    if dry_run:
                        print(f"  [dry-run] Would set {labels_desc} on #{number}: {issue['title']}")
                        updated += 1
                    else:
                        try:
                            self.set_org_issue_field_values(
                                repository, number,
                                [(fid, val) for fid, val, _ in fields_to_write]
                            )
                            print(f"  ✅ Set {labels_desc} on #{number}: {issue['title']}")
                            updated += 1
                        except GitHubAPIError as e:
                            print(f"  ❌ #{number}: {e}", file=sys.stderr)

        print(f"\n{'[dry-run] ' if dry_run else ''}{'Would update' if dry_run else 'Updated'} {updated} issue(s)")
        return updated

    def set_product_field(
        self,
        repository: str,
        issue_number: int,
        org: str,
        config_path: str,
        field_name: str = "Product"
    ) -> bool:
        """Set the org-level Product field on an issue.

        Returns True on success or benign skip, False on hard failure.
        """
        if not os.path.exists(config_path):
            print(f"⚠️  Products config not found: {config_path}", file=sys.stderr)
            return False

        products = self._load_products_config(config_path)
        repo_name = repository.split('/')[-1]
        product_name = self._find_product_for_repo(products, repo_name)

        if not product_name:
            print(f"ℹ️  No product mapping found for '{repo_name}' — skipping '{field_name}' field")
            return True

        print(f"Repo '{repo_name}' → product '{product_name}'")

        try:
            field_data = self.get_org_issue_field(org, field_name)
            if not field_data:
                print(f"ℹ️  No '{field_name}' org issue field found — skipping")
                return True

            field_id = field_data['id']
            options = field_data.get('options', [])
            if options:
                valid_names = [o['name'] for o in options]
                if product_name not in valid_names:
                    print(
                        f"⚠️  '{product_name}' is not a valid option for org '{field_name}'. "
                        f"Available: {valid_names}",
                        file=sys.stderr
                    )
                    return False

            self.set_org_issue_field_value(repository, issue_number, field_id, product_name)
            print(f"✅ Set org '{field_name}' to '{product_name}' on {repository}#{issue_number}")
            return True

        except GitHubAPIError as e:
            print(f"❌ {e}", file=sys.stderr)
            return False


def main():
    """Main entry point for CLI usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="GitHub Projects V2 automation for sprint management"
    )
    parser.add_argument(
        "action",
        choices=[
            "add-to-sprint", "remove-from-sprint",
            "add-to-build-project", "remove-from-build-project",
            "sync-fields", "backfill-fields", "cascade-label",
        ],
        help="Action to perform"
    )
    parser.add_argument(
        "--repository",
        help="Repository in org/repo format (required for most actions)"
    )
    parser.add_argument(
        "--issue-number",
        type=int,
        help="Issue number (required for most actions)"
    )
    parser.add_argument(
        "--org",
        required=False,
        default=None,
        help="Organization name (required for most actions except cascade-label)"
    )
    parser.add_argument(
        "--label",
        help="Build label (required for add-to-build-project action)"
    )
    parser.add_argument(
        "--set-sprint-if-backlog",
        action="store_true",
        default=False,
        help="For add-to-build-project: also set current sprint if sprint-backlog label is present"
    )
    parser.add_argument(
        "--config",
        help="Path to pds-products.yaml"
    )
    parser.add_argument(
        "--set-product-field",
        action="store_true",
        default=False,
        help="For sync-fields: set the org-level Product field"
    )
    parser.add_argument(
        "--set-work-area",
        action="store_true",
        default=False,
        help="For sync-fields: set the org-level Work Area field (cascades to sub-issues)"
    )
    parser.add_argument(
        "--field-name",
        default="Product",
        help="Single-select field name to use for --set-product-field (default: Product)"
    )
    parser.add_argument(
        "--no-cascade",
        action="store_true",
        default=False,
        help="For sync-fields --set-work-area: skip cascading work area to sub-issues"
    )
    parser.add_argument(
        "--work-area",
        action="store_true",
        default=False,
        help="For backfill-fields: backfill the Work Area field"
    )
    parser.add_argument(
        "--product",
        action="store_true",
        default=False,
        help="For backfill-fields: backfill the Product field"
    )
    parser.add_argument(
        "--repo",
        help="For backfill-fields: limit to a single repo name"
    )
    parser.add_argument(
        "--label-action",
        choices=["add", "remove"],
        default="add",
        help="For cascade-label: whether to add or remove the label on sub-issues (default: add)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="For backfill-fields: print what would be done without making changes"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="For backfill-fields: re-set fields even if already set"
    )

    args = parser.parse_args()

    ORG_REQUIRED = {
        "add-to-sprint", "remove-from-sprint",
        "add-to-build-project", "remove-from-build-project",
        "sync-fields", "backfill-fields",
    }
    if args.action in ORG_REQUIRED and not args.org:
        print(f"❌ --org is required for {args.action}", file=sys.stderr)
        sys.exit(1)

    automation = GitHubProjectAutomation()

    if args.action == "sync-fields":
        if not args.repository or args.issue_number is None:
            print("❌ --repository and --issue-number are required for sync-fields", file=sys.stderr)
            sys.exit(1)
        if not args.config:
            print("❌ --config is required for sync-fields", file=sys.stderr)
            sys.exit(1)
        if not args.set_product_field and not args.set_work_area:
            print("❌ at least one of --set-product-field or --set-work-area is required", file=sys.stderr)
            sys.exit(1)

        success = automation.sync_fields(
            args.repository,
            args.issue_number,
            args.org,
            args.config,
            set_product=args.set_product_field,
            set_work_area=args.set_work_area,
            cascade=not args.no_cascade,
            field_name=args.field_name
        )
        sys.exit(0 if success else 1)

    elif args.action == "cascade-label":
        if not args.repository or args.issue_number is None:
            print("❌ --repository and --issue-number are required for cascade-label", file=sys.stderr)
            sys.exit(1)
        if not args.label:
            print("❌ --label is required for cascade-label", file=sys.stderr)
            sys.exit(1)
        count = automation.cascade_label_to_sub_issues(
            args.repository,
            args.issue_number,
            args.label,
            action=args.label_action
        )
        print(f"{'Added' if args.label_action == 'add' else 'Removed'} '{args.label}' on {count} sub-issue(s)")
        sys.exit(0)

    elif args.action == "backfill-fields":
        if not args.config:
            print("❌ --config is required for backfill-fields", file=sys.stderr)
            sys.exit(1)
        if not args.work_area and not args.product:
            print("❌ at least one of --work-area or --product is required for backfill-fields", file=sys.stderr)
            sys.exit(1)
        automation.backfill_fields(
            args.org,
            args.config,
            backfill_work_area=args.work_area,
            backfill_product=args.product,
            repo_filter=args.repo,
            dry_run=args.dry_run,
            force=args.force
        )
        sys.exit(0)

    elif args.action == "add-to-build-project":
        if not args.repository or args.issue_number is None:
            print("❌ --repository and --issue-number are required for add-to-build-project", file=sys.stderr)
            sys.exit(1)
        if not args.label:
            print("❌ --label is required for add-to-build-project action", file=sys.stderr)
            sys.exit(1)

        success = automation.add_issue_to_build_project(
            args.repository,
            args.issue_number,
            args.org,
            args.label,
            set_sprint_if_backlog=args.set_sprint_if_backlog
        )
        sys.exit(0 if success else 1)

    elif args.action == "remove-from-build-project":
        if not args.repository or args.issue_number is None:
            print("❌ --repository and --issue-number are required for remove-from-build-project", file=sys.stderr)
            sys.exit(1)
        if not args.label:
            print("❌ --label is required for remove-from-build-project action", file=sys.stderr)
            sys.exit(1)

        success = automation.remove_issue_from_build_project(
            args.repository,
            args.issue_number,
            args.org,
            args.label
        )
        sys.exit(0 if success else 1)

    else:  # add-to-sprint / remove-from-sprint
        if not args.repository or args.issue_number is None:
            print("❌ --repository and --issue-number are required", file=sys.stderr)
            sys.exit(1)
        action = "add" if args.action == "add-to-sprint" else "remove"
        success_count = automation.process_sprint_for_build_labels(
            args.repository,
            args.issue_number,
            args.org,
            action
        )

        # Exit with error if no projects were updated and we expected updates
        if success_count == 0:
            # Check if there were any build labels - if yes, it's an error
            try:
                labels = automation.get_labels_by_prefix(args.repository, args.issue_number, "B")
                if labels:
                    sys.exit(1)
            except GitHubAPIError:
                sys.exit(1)


if __name__ == "__main__":
    main()
