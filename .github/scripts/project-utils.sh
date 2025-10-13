#!/bin/bash
# Utility functions for GitHub Projects V2 operations

set -e

# Get issue node ID from repository and issue number
# Usage: get_issue_id <repository> <issue_number>
# Returns: Issue node ID
get_issue_id() {
    local repository=$1
    local issue_number=$2

    gh api "repos/${repository}/issues/${issue_number}" --jq '.node_id'
}

# Get project ID from project number
# Usage: get_project_id_by_number <org> <project_number>
# Returns: Project ID
get_project_id_by_number() {
    local org=$1
    local project_number=$2

    gh api graphql -f query="
        query {
            organization(login: \"$org\") {
                projectsV2(first: 100) {
                    nodes {
                        id
                        number
                    }
                }
            }
        }" --jq ".data.organization.projectsV2.nodes[] | select(.number == $project_number) | .id"
}

# Get project data (id, number) from project title
# Usage: get_project_by_title <org> <project_title>
# Returns: JSON with id and number fields
get_project_by_title() {
    local org=$1
    local title=$2

    gh api graphql -f query="
        query {
            organization(login: \"$org\") {
                projectsV2(first: 100) {
                    nodes {
                        id
                        number
                        title
                    }
                }
            }
        }" --jq ".data.organization.projectsV2.nodes[] | select(.title == \"$title\")"
}

# Check if issue is already in project
# Usage: is_issue_in_project <project_id> <issue_id>
# Returns: Item ID if found, empty string if not
is_issue_in_project() {
    local project_id=$1
    local issue_id=$2

    gh api graphql -f query="
        query {
            node(id: \"$project_id\") {
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
        }" --jq ".data.node.items.nodes[] | select(.content.id == \"$issue_id\") | .id"
}

# Add issue to project
# Usage: add_issue_to_project <project_id> <issue_id>
# Returns: Item ID of the added issue
add_issue_to_project() {
    local project_id=$1
    local issue_id=$2

    gh api graphql -f query="
        mutation {
            addProjectV2ItemById(input: {projectId: \"$project_id\", contentId: \"$issue_id\"}) {
                item {
                    id
                }
            }
        }" --jq '.data.addProjectV2ItemById.item.id'
}

# Get or add issue to project (idempotent)
# Usage: ensure_issue_in_project <project_id> <issue_id>
# Returns: Item ID
ensure_issue_in_project() {
    local project_id=$1
    local issue_id=$2

    local item_id=$(is_issue_in_project "$project_id" "$issue_id")

    if [ -n "$item_id" ]; then
        echo "$item_id"
    else
        add_issue_to_project "$project_id" "$issue_id"
    fi
}

# Get iteration field data from project
# Usage: get_iteration_field <project_id>
# Returns: JSON with field id and configuration
get_iteration_field() {
    local project_id=$1

    gh api graphql -f query="
        query {
            node(id: \"$project_id\") {
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
        }" --jq '.data.node.fields.nodes[] | select(.name == "Iteration")'
}

# Set iteration field to current iteration
# Usage: set_iteration_to_current <project_id> <item_id>
# Returns: Success (0) or failure (1)
set_iteration_to_current() {
    local project_id=$1
    local item_id=$2

    # Get iteration field data
    local field_data=$(get_iteration_field "$project_id")

    if [ -z "$field_data" ]; then
        echo "⚠️  No Iteration field found" >&2
        return 1
    fi

    local field_id=$(echo "$field_data" | jq -r '.id')
    local current_iteration_id=$(echo "$field_data" | jq -r '.configuration.iterations[0].id')

    if [ -z "$current_iteration_id" ] || [ "$current_iteration_id" == "null" ]; then
        echo "⚠️  No current iteration found" >&2
        return 1
    fi

    # Update the iteration field
    gh api graphql -f query="
        mutation {
            updateProjectV2ItemFieldValue(input: {
                projectId: \"$project_id\"
                itemId: \"$item_id\"
                fieldId: \"$field_id\"
                value: {
                    iterationId: \"$current_iteration_id\"
                }
            }) {
                projectV2Item {
                    id
                }
            }
        }" > /dev/null

    return $?
}

# Get all labels starting with a prefix from an issue
# Usage: get_labels_by_prefix <repository> <issue_number> <prefix>
# Returns: List of label names (one per line)
get_labels_by_prefix() {
    local repository=$1
    local issue_number=$2
    local prefix=$3

    gh api "repos/${repository}/issues/${issue_number}" \
        --jq ".labels[].name | select(startswith(\"$prefix\"))"
}
