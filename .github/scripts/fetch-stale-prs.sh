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
GQL_TEMPLATE=$(cat <<'GRAPHQL'
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

GQL_TEMPLATE="${GQL_TEMPLATE/__CUTOFF__/$CUTOFF}"

# Retry a single gh api graphql call (without --paginate).
# Writes raw JSON to TMPFILE on success, returns non-zero on failure.
# Args: $1 = query string, $2 = tmpfile path
MAX_ATTEMPTS=8
INITIAL_BACKOFF=15

call_with_retry() {
  local query="$1"
  local tmpfile="$2"
  local backoff=$INITIAL_BACKOFF

  for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    local gh_exit=0
    echo "  gh call attempt $attempt/$MAX_ATTEMPTS..." >&2
    gh api graphql -f query="$query" > "$tmpfile" 2>&1 || gh_exit=$?

    if [ "$gh_exit" -eq 0 ] && \
       head -c1 "$tmpfile" | grep -q '{' && \
       ! grep -qiE '<html|HTTP 502|HTTP 504|Bad Gateway|503 Service|504 Gateway' "$tmpfile" 2>/dev/null; then
      return 0
    fi

    echo "  attempt $attempt failed (exit=$gh_exit):" >&2
    head -5 "$tmpfile" >&2

    if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
      echo "  retrying in ${backoff}s..." >&2
      sleep "$backoff"
      backoff=$(( backoff * 2 ))
    fi
  done

  echo "  all $MAX_ATTEMPTS attempts failed" >&2
  return 1
}

PAGEFILE=$(mktemp)
ALLFILE=$(mktemp)
trap 'rm -f "$PAGEFILE" "$ALLFILE"' EXIT

# Manual pagination: fetch one page at a time so each page can be retried
# independently without restarting from the beginning.
end_cursor="null"
page=0

while true; do
  page=$(( page + 1 ))
  echo "Fetching page $page (cursor: $end_cursor)..." >&2

  # Build a query with the cursor inlined as a literal. The variable
  # declaration must also be removed — GitHub's API rejects unused variables.
  if [ "$end_cursor" = "null" ]; then
    paged_query=$(echo "$GQL_TEMPLATE" \
      | sed 's/query(\$endCursor: String)/query()/' \
      | sed 's/after: \$endCursor/after: null/')
  else
    paged_query=$(echo "$GQL_TEMPLATE" \
      | sed 's/query(\$endCursor: String)/query()/' \
      | sed "s/after: \\\$endCursor/after: $end_cursor/")
  fi

  if ! call_with_retry "$paged_query" "$PAGEFILE"; then
    echo "Error: page $page fetch failed after $MAX_ATTEMPTS attempts — giving up" >&2
    exit 1
  fi

  # Append this page's nodes to the accumulated file
  jq -c '.data.search.nodes[] | select(type == "object")' "$PAGEFILE" >> "$ALLFILE"

  has_next=$(jq -r '.data.search.pageInfo.hasNextPage' "$PAGEFILE")
  if [ "$has_next" != "true" ]; then
    break
  fi

  end_cursor=$(jq -r '.data.search.pageInfo.endCursor' "$PAGEFILE")
  # Wrap cursor in quotes for GraphQL string literal
  end_cursor="\"${end_cursor}\""
done

cp "$ALLFILE" "$OUTPUT"

COUNT=$(wc -l < "$OUTPUT" | tr -d ' ')
echo "Found $COUNT PRs across $page page(s) → $OUTPUT" >&2
echo "$COUNT"
