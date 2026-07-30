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
        latestReviews(first: 10) {
          nodes { author { login } state }
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

TMPFILE=$(mktemp)
trap 'rm -f "$TMPFILE"' EXIT

# Retry wrapper: up to MAX_ATTEMPTS with exponential backoff.
# Retries on non-zero exit or a non-JSON (e.g. HTML 502) response body.
# Note: 'gh' is called with '|| true' so set -e doesn't fire mid-loop;
# GH_EXIT is checked explicitly instead.
MAX_ATTEMPTS=4
BACKOFF=5
GH_EXIT=0
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  echo "Attempt $attempt/$MAX_ATTEMPTS: calling gh api graphql..." >&2
  gh api graphql --paginate -f query="$GQL" > "$TMPFILE" 2>&1 || GH_EXIT=$?

  if [ "$GH_EXIT" -ne 0 ]; then
    echo "Attempt $attempt/$MAX_ATTEMPTS: gh exited $GH_EXIT — response body:" >&2
    cat "$TMPFILE" >&2
  elif ! head -c1 "$TMPFILE" | grep -q '{'; then
    echo "Attempt $attempt/$MAX_ATTEMPTS: non-JSON response (expected '{'), body:" >&2
    head -10 "$TMPFILE" >&2
    GH_EXIT=1
  else
    echo "Attempt $attempt/$MAX_ATTEMPTS: success" >&2
    break
  fi

  if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
    echo "Retrying in ${BACKOFF}s..." >&2
    sleep "$BACKOFF"
    BACKOFF=$(( BACKOFF * 2 ))
    GH_EXIT=0
  fi
done

if [ "$GH_EXIT" -ne 0 ]; then
  echo "Error: gh api graphql failed after $MAX_ATTEMPTS attempts — giving up" >&2
  exit 1
fi

# Each page is a complete JSON object on its own line; extract PR nodes from all pages
if ! jq -r '.data.search.nodes[]' "$TMPFILE" > "$OUTPUT" 2>&1; then
  echo "Error: jq failed to parse gh api output:" >&2
  head -5 "$TMPFILE" >&2
  exit 1
fi

COUNT=$(jq -s 'length' "$OUTPUT")
echo "Found $COUNT PRs → $OUTPUT" >&2
echo "$COUNT"
