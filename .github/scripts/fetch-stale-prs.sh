#!/usr/bin/env bash
# Fetch open PRs created more than 3 days ago from the NASA-PDS org.
#
# Usage:
#   fetch-stale-prs.sh [output_file]   (default: stale_prs.json)
#
# Requires GH_TOKEN in the environment.
#
# Local test example:
#   GH_TOKEN=$(gh auth token) ./fetch-stale-prs.sh
set -euo pipefail

OUTPUT="${1:-stale_prs.json}"

CUTOFF=$(date -u -d '3 days ago' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
  || date -u -v-3d '+%Y-%m-%dT%H:%M:%SZ')

echo "Fetching PRs created before $CUTOFF ..." >&2

# Single-quoted heredoc: no shell substitution — $endCursor stays literal
# for GraphQL. Cutoff is spliced in via sed after the fact.
GQL=$(cat <<'GRAPHQL'
query($endCursor: String) {
  search(
    query: "org:NASA-PDS is:pr is:open draft:false created:<__CUTOFF__"
    type: ISSUE
    first: 100
    after: $endCursor
  ) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        title
        url
        createdAt
        author { login }
        repository { nameWithOwner }
        reviewRequests(first: 5) {
          nodes { requestedReviewer { ... on User { login } } }
        }
        labels(first: 5) { nodes { name } }
        reviewDecision
      }
    }
  }
}
GRAPHQL
)

GQL="${GQL/__CUTOFF__/$CUTOFF}"

gh api graphql --paginate \
  -f query="$GQL" \
  --jq '.data.search.nodes[]' > "$OUTPUT"

COUNT=$(jq -s 'length' "$OUTPUT")
echo "Found $COUNT PRs → $OUTPUT" >&2
echo "$COUNT"
