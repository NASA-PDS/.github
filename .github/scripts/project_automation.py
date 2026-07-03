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

    def _set_project_product_field_on_item(
        self,
        project_id: str,
        item_id: str,
        repo_name: str,
        config_path: str,
        field_name: str = "Product"
    ) -> bool:
        """Set a single-select product field on an existing project item."""
        products = self._load_products_config(config_path)
        product_name = self._find_product_for_repo(products, repo_name)
        if not product_name:
            print(f"ℹ️  No product mapping for '{repo_name}' — skipping project '{field_name}' field")
            return True

        try:
            field_data = self.get_project_single_select_field(project_id, field_name)
            if not field_data:
                print(f"ℹ️  No '{field_name}' field on project — skipping")
                return True

            field_id = field_data['id']
            options = field_data.get('options', [])
            option_id = next(
                (o['id'] for o in options if o['name'].lower() == product_name.lower()),
                None
            )
            if not option_id:
                available = [o['name'] for o in options]
                print(
                    f"⚠️  No option matching '{product_name}' in project '{field_name}'. "
                    f"Available: {available}",
                    file=sys.stderr
                )
                return False

            self.set_project_single_select_field(project_id, item_id, field_id, option_id)
            print(f"✅ Set project '{field_name}' to '{product_name}'")
            return True

        except GitHubAPIError as e:
            print(f"⚠️  Could not set project '{field_name}': {e}", file=sys.stderr)
            return False

    def add_issue_to_build_project(
        self,
        repository: str,
        issue_number: int,
        org: str,
        label: str,
        set_sprint_if_backlog: bool = False,
        config_path: Optional[str] = None
    ) -> bool:
        """
        Add an issue to all build projects matching the label title.

        Args:
            repository: Repository in org/repo format
            issue_number: Issue number
            org: Organization name
            label: Build label (e.g., "B16")
            set_sprint_if_backlog: If True, also set current sprint when sprint-backlog label is present
            config_path: Path to pds-products.yaml; when provided, also sets the Product field

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

                # Set Product field on project item if config provided
                if config_path and os.path.exists(config_path):
                    self._set_project_product_field_on_item(project_id, item_id, repo_name, config_path)

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

    def set_project_product_field(
        self,
        repository: str,
        issue_number: int,
        org: str,
        project_number: int,
        config_path: str,
        field_name: str = "Product"
    ) -> bool:
        """Set a single-select field on a project item based on pds-products.yaml.

        Returns True on success or benign skip, False on hard failure.
        """
        if not os.path.exists(config_path):
            print(f"⚠️  Products config not found: {config_path}", file=sys.stderr)
            return False

        products = self._load_products_config(config_path)
        repo_name = repository.split('/')[-1]
        product_name = self._find_product_for_repo(products, repo_name)

        if not product_name:
            print(f"ℹ️  No product mapping for '{repo_name}' — skipping project '{field_name}' field")
            return True

        print(f"Repo '{repo_name}' → product '{product_name}'")

        try:
            project_id = self.get_project_id_by_number(org, project_number)
            if not project_id:
                print(f"❌ Could not find project #{project_number}", file=sys.stderr)
                return False

            issue_id = self.get_issue_id(repository, issue_number)
            item_id = self.ensure_issue_in_project(project_id, issue_id)

            field_data = self.get_project_single_select_field(project_id, field_name)
            if not field_data:
                print(f"ℹ️  No '{field_name}' field on project #{project_number} — skipping")
                return True

            field_id = field_data['id']
            options = field_data.get('options', [])
            option_id = next(
                (o['id'] for o in options if o['name'].lower() == product_name.lower()),
                None
            )

            if not option_id:
                available = [o['name'] for o in options]
                print(
                    f"⚠️  No option matching '{product_name}' in project '{field_name}' field. "
                    f"Available: {available}",
                    file=sys.stderr
                )
                return False

            self.set_project_single_select_field(project_id, item_id, field_id, option_id)
            print(f"✅ Set project '{field_name}' to '{product_name}' on project #{project_number} (item {item_id})")
            return True

        except GitHubAPIError as e:
            print(f"❌ {e}", file=sys.stderr)
            return False

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
        """Set an org-level issue field value on an issue via REST PUT."""
        body = json.dumps({"issue_field_values": [{"field_id": field_id, "value": value}]})
        cmd = ["gh", "api", "-X", "PUT",
               f"repos/{repository}/issues/{issue_number}/issue-field-values",
               "--input", "-"]
        try:
            subprocess.run(cmd, input=body, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            raise GitHubAPIError(f"Failed to set org issue field value: {error_msg}")

    @staticmethod
    def _load_products_config(config_path: str) -> Dict[str, Any]:
        """Parse pds-products.yaml without external dependencies.

        Returns a dict keyed by product name with 'repositories', 'github_project_name',
        and 'ignore' entries.
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

    def set_product_field(
        self,
        repository: str,
        issue_number: int,
        org: str,
        config_path: str,
        field_name: str = "Product",
        project_numbers: Optional[List[int]] = None
    ) -> bool:
        """Set the Product field at both the org level and on any specified project items.

        Args:
            repository: Repository in org/repo format
            issue_number: Issue number
            org: Organization name
            config_path: Path to pds-products.yaml
            field_name: Field name to set (default: Product)
            project_numbers: Optional list of project numbers to also set the field on

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

        overall_success = True

        # ── Org-level field ──────────────────────────────────────────────────
        try:
            field_data = self.get_org_issue_field(org, field_name)
            if not field_data:
                print(f"ℹ️  No '{field_name}' org issue field found — skipping org field")
            else:
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
                        overall_success = False
                    else:
                        self.set_org_issue_field_value(repository, issue_number, field_id, product_name)
                        print(f"✅ Set org '{field_name}' to '{product_name}' on {repository}#{issue_number}")
                else:
                    self.set_org_issue_field_value(repository, issue_number, field_id, product_name)
                    print(f"✅ Set org '{field_name}' to '{product_name}' on {repository}#{issue_number}")
        except GitHubAPIError as e:
            print(f"❌ Org field: {e}", file=sys.stderr)
            overall_success = False

        # ── Project-level fields ─────────────────────────────────────────────
        if project_numbers:
            try:
                issue_id = self.get_issue_id(repository, issue_number)
            except GitHubAPIError as e:
                print(f"❌ Could not get issue node ID: {e}", file=sys.stderr)
                return False

            for project_number in project_numbers:
                try:
                    project_id = self.get_project_id_by_number(org, project_number)
                    if not project_id:
                        print(f"⚠️  Could not find project #{project_number} — skipping", file=sys.stderr)
                        continue
                    item_id = self.ensure_issue_in_project(project_id, issue_id)
                    self._set_project_product_field_on_item(
                        project_id, item_id, repo_name, config_path, field_name
                    )
                except GitHubAPIError as e:
                    print(f"⚠️  Project #{project_number} field: {e}", file=sys.stderr)

        return overall_success


def main():
    """Main entry point for CLI usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="GitHub Projects V2 automation for sprint management"
    )
    parser.add_argument(
        "action",
        choices=["add-to-sprint", "remove-from-sprint", "add-to-build-project", "set-product-field"],
        help="Action to perform"
    )
    parser.add_argument(
        "--repository",
        required=True,
        help="Repository in org/repo format"
    )
    parser.add_argument(
        "--issue-number",
        type=int,
        required=True,
        help="Issue number"
    )
    parser.add_argument(
        "--org",
        required=True,
        help="Organization name"
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
        help="Path to pds-products.yaml (required for set-product-field; optional for add-to-build-project to also set the project Product field)"
    )
    parser.add_argument(
        "--field-name",
        default="Product",
        help="Single-select field name to set (default: Product)"
    )
    parser.add_argument(
        "--project-numbers",
        help="Comma-separated project numbers to also set the field on (for set-product-field)"
    )

    args = parser.parse_args()

    automation = GitHubProjectAutomation()

    if args.action == "set-product-field":
        if not args.config:
            print("❌ --config is required for set-product-field", file=sys.stderr)
            sys.exit(1)
        project_numbers = None
        if args.project_numbers:
            project_numbers = [int(n.strip()) for n in args.project_numbers.split(',') if n.strip()]
        success = automation.set_product_field(
            args.repository,
            args.issue_number,
            args.org,
            args.config,
            field_name=args.field_name,
            project_numbers=project_numbers
        )
        sys.exit(0 if success else 1)

    elif args.action == "add-to-build-project":
        if not args.label:
            print("❌ --label is required for add-to-build-project action", file=sys.stderr)
            sys.exit(1)

        success = automation.add_issue_to_build_project(
            args.repository,
            args.issue_number,
            args.org,
            args.label,
            set_sprint_if_backlog=args.set_sprint_if_backlog,
            config_path=args.config
        )
        sys.exit(0 if success else 1)

    else:  # add-to-sprint / remove-from-sprint
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
