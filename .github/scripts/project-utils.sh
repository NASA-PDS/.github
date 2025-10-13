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
        }" --jq '.data.node.fields.nodes[] | select(.name == "Iteration" or .name == "Sprint")'
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

# Clear iteration field (set to null)
# Usage: clear_iteration <project_id> <item_id>
# Returns: Success (0) or failure (1)
clear_iteration() {
    local project_id=$1
    local item_id=$2

    # Get iteration field data
    local field_data=$(get_iteration_field "$project_id")

    if [ -z "$field_data" ]; then
        echo "⚠️  No Sprint/Iteration field found" >&2
        return 1
    fi

    local field_id=$(echo "$field_data" | jq -r '.id')

    # Clear the iteration field by setting it to null
    gh api graphql -f query="
        mutation {
            clearProjectV2ItemFieldValue(input: {
                projectId: \"$project_id\"
                itemId: \"$item_id\"
                fieldId: \"$field_id\"
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

# Add issue to sprint (iteration:@current) for all build projects
# Usage: add_to_sprint <repository> <issue_number> <org>
# Returns: Number of projects updated (0 if none)
add_to_sprint() {
    local repository=$1
    local issue_number=$2
    local org=$3

    echo "Processing sprint-backlog label"

    # Get issue node ID
    local issue_id=$(get_issue_id "$repository" "$issue_number")
    echo "Issue node ID: $issue_id"

    # Find all build labels on this issue
    local build_labels=$(get_labels_by_prefix "$repository" "$issue_number" "B")

    if [ -z "$build_labels" ]; then
        echo "⚠️  No build label found on issue"
        echo "ℹ️  Please add a build label (e.g., B16, B17) before adding sprint-backlog"
        return 0
    fi

    echo "Found build labels:"
    echo "$build_labels"
    echo ""

    # Process each build label
    local success_count=0
    while IFS= read -r build_label; do
        echo "Processing iteration for build: $build_label"

        # Find the project with matching title
        local project_data=$(get_project_by_title "$org" "$build_label")

        if [ -z "$project_data" ]; then
            echo "⚠️  No project found for build '$build_label' - skipping"
            echo ""
            continue
        fi

        local project_id=$(echo "$project_data" | jq -r '.id')
        local project_number=$(echo "$project_data" | jq -r '.number')

        echo "Found project #$project_number: $build_label"

        # Ensure issue is in project
        local item_id=$(ensure_issue_in_project "$project_id" "$issue_id")

        if [ -z "$item_id" ]; then
            echo "❌ Failed to add issue to project #$project_number"
            echo ""
            continue
        fi

        echo "✅ Issue in project (item: $item_id)"

        # Set iteration to current
        if set_iteration_to_current "$project_id" "$item_id"; then
            echo "✅ Set iteration to @current in project #$project_number"
            success_count=$((success_count + 1))
        else
            echo "❌ Failed to set iteration in project #$project_number"
        fi
        echo ""
    done <<< "$build_labels"

    if [ $success_count -gt 0 ]; then
        echo "✅ Sprint-backlog processing complete ($success_count project(s) updated)"
    else
        echo "⚠️  No projects were updated"
    fi

    return 0
}

# Remove issue from sprint (clear iteration field) for all build projects
# Usage: remove_from_sprint <repository> <issue_number> <org>
# Returns: Number of projects updated (0 if none)
remove_from_sprint() {
    local repository=$1
    local issue_number=$2
    local org=$3

    echo "Removing from sprint (sprint-backlog label removed)"

    # Get issue node ID
    local issue_id=$(get_issue_id "$repository" "$issue_number")
    echo "Issue node ID: $issue_id"

    # Find all build labels on this issue
    local build_labels=$(get_labels_by_prefix "$repository" "$issue_number" "B")

    if [ -z "$build_labels" ]; then
        echo "ℹ️  No build labels found on issue - nothing to clear"
        return 0
    fi

    echo "Found build labels:"
    echo "$build_labels"
    echo ""

    # Process each build label
    local success_count=0
    while IFS= read -r build_label; do
        echo "Clearing sprint for build: $build_label"

        # Find the project with matching title
        local project_data=$(get_project_by_title "$org" "$build_label")

        if [ -z "$project_data" ]; then
            echo "⚠️  No project found for build '$build_label' - skipping"
            echo ""
            continue
        fi

        local project_id=$(echo "$project_data" | jq -r '.id')
        local project_number=$(echo "$project_data" | jq -r '.number')

        echo "Found project #$project_number: $build_label"

        # Check if issue is in project
        local item_id=$(is_issue_in_project "$project_id" "$issue_id")

        if [ -z "$item_id" ]; then
            echo "ℹ️  Issue not in project #$project_number - nothing to clear"
            echo ""
            continue
        fi

        echo "✅ Issue in project (item: $item_id)"

        # Clear the sprint/iteration field
        if clear_iteration "$project_id" "$item_id"; then
            echo "✅ Cleared sprint in project #$project_number"
            success_count=$((success_count + 1))
        else
            echo "❌ Failed to clear sprint in project #$project_number"
        fi
        echo ""
    done <<< "$build_labels"

    if [ $success_count -gt 0 ]; then
        echo "✅ Sprint removal complete ($success_count project(s) updated)"
    else
        echo "⚠️  No projects were updated"
    fi

    return 0
}
