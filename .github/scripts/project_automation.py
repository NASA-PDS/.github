#!/usr/bin/env python3
"""
GitHub Projects V2 automation utilities.

This script provides automation for managing issues in GitHub Projects V2,
including adding issues to projects and managing sprint iterations.
"""

import subprocess
import json
import sys
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

    def get_project_by_title(self, org: str, title: str) -> Optional[Dict[str, Any]]:
        """
        Get project data (id, number) from project title.

        Args:
            org: Organization name
            title: Project title

        Returns:
            Dictionary with 'id', 'number', and 'title' keys, or None if not found

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
                "--jq", f'.data.organization.projectsV2.nodes[] | select(.title == "{title}")'
            ])

            if not result:
                return None

            return json.loads(result)
        except (GitHubAPIError, json.JSONDecodeError) as e:
            raise GitHubAPIError(f"Failed to get project by title: {e}")

    def is_issue_in_project(self, project_id: str, issue_id: str) -> Optional[str]:
        """
        Check if issue is already in project.

        Args:
            project_id: Project node ID
            issue_id: Issue node ID

        Returns:
            Item ID if found, None if not in project

        Raises:
            GitHubAPIError: If the API call fails
        """
        query = """
        query($projectId: ID!) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    items(first: 100) {
                        nodes {
                            id
                            content {
                                ... on Issue {
                                    id
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
                "--jq", f'.data.node.items.nodes[] | select(.content.id == "{issue_id}") | .id'
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

                # Find the project with matching title
                project_data = self.get_project_by_title(org, build_label)

                if not project_data:
                    print(f"⚠️  No project found for build '{build_label}' - skipping")
                    print()
                    continue

                project_id = project_data['id']
                project_number = project_data['number']

                print(f"Found project #{project_number}: {build_label}")

                if action == "add":
                    # Ensure issue is in project
                    item_id = self.ensure_issue_in_project(project_id, issue_id)

                    if not item_id:
                        print(f"❌ Failed to add issue to project #{project_number}")
                        print()
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
                        print()
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


    def add_issue_to_build_project(
        self,
        repository: str,
        issue_number: int,
        org: str,
        label: str
    ) -> bool:
        """
        Add an issue to a build project based on label.

        Args:
            repository: Repository in org/repo format
            issue_number: Issue number
            org: Organization name
            label: Build label (e.g., "B16")

        Returns:
            True if successful, False otherwise
        """
        print(f"Processing build label: {label}")

        try:
            # Get issue node ID
            issue_id = self.get_issue_id(repository, issue_number)
            print(f"Issue node ID: {issue_id}")

            # Find project with matching title
            project_data = self.get_project_by_title(org, label)

            if not project_data:
                print(f"⚠️  No project found with title '{label}' - skipping")
                return False

            project_id = project_data['id']
            project_number = project_data['number']

            print(f"Found project #{project_number}: {label}")
            print(f"Project ID: {project_id}")

            # Add issue to project (idempotent)
            item_id = self.ensure_issue_in_project(project_id, issue_id)

            if item_id:
                print(f"✅ Issue in project #{project_number} (item: {item_id})")
                return True
            else:
                print(f"❌ Failed to add to project #{project_number}")
                return False

        except GitHubAPIError as e:
            print(f"❌ {e}", file=sys.stderr)
            sys.exit(1)


def main():
    """Main entry point for CLI usage."""
    import argparse

    parser = argparse.ArgumentParser(
        description="GitHub Projects V2 automation for sprint management"
    )
    parser.add_argument(
        "action",
        choices=["add-to-sprint", "remove-from-sprint", "add-to-build-project"],
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

    args = parser.parse_args()

    automation = GitHubProjectAutomation()

    if args.action == "add-to-build-project":
        if not args.label:
            print("❌ --label is required for add-to-build-project action", file=sys.stderr)
            sys.exit(1)

        success = automation.add_issue_to_build_project(
            args.repository,
            args.issue_number,
            args.org,
            args.label
        )
        sys.exit(0 if success else 1)

    else:
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
