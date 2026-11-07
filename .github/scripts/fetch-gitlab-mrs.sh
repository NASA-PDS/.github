#!/usr/bin/env bash
# Fetch open, non-draft GitLab merge requests created more than 3 days ago from
# a GitLab group (including its subgroups).
#
# Usage:
#   fetch-gitlab-mrs.sh [output_file]   (default: gitlab_mrs.json)
#
# Requires in the environment:
#   GITLAB_TOKEN     token with read_api on the group
#   GITLAB_API_URL   GitLab API base URL, e.g. https://<gitlab-host>/api/v4
#   GITLAB_GROUP     group id or full group path
# If GITLAB_TOKEN is unset the script writes an empty file and prints 0, so the
# workflow keeps working before GitLab is configured.
#
# Each merge request is converted to the same JSON shape as a PR node written by
# fetch-stale-prs.sh, so build-slack-payload.sh renders both without changes.
# Output is one JSON object per line. Only the MR count is printed on stdout.
#
# This repository is public and its workflow logs are public: never print the
# GitLab host, response bodies, or MR details. Errors report HTTP status codes only.
#
# Local test example:
#   GITLAB_TOKEN="..." GITLAB_API_URL="https://<gitlab-host>/api/v4" \
#     GITLAB_GROUP="<group-path>" ./fetch-gitlab-mrs.sh
set -euo pipefail

OUTPUT="${1:-gitlab_mrs.json}"
PER_PAGE="${PER_PAGE:-100}"

if [ -z "${GITLAB_TOKEN:-}" ]; then
  echo "GITLAB_TOKEN is not set; skipping GitLab merge requests" >&2
  : > "$OUTPUT"
  echo 0
  exit 0
fi

: "${GITLAB_API_URL:?GITLAB_API_URL is required when GITLAB_TOKEN is set}"
: "${GITLAB_GROUP:?GITLAB_GROUP is required when GITLAB_TOKEN is set}"

CUTOFF_EPOCH=$(( $(date -u +%s) - 3 * 86400 ))
CUTOFF=$(date -u -d "@${CUTOFF_EPOCH}" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
  || date -u -r "${CUTOFF_EPOCH}" '+%Y-%m-%dT%H:%M:%SZ')

GROUP_ENC=$(jq -rn --arg g "$GITLAB_GROUP" '$g | @uri')

echo "Fetching GitLab MRs created before $CUTOFF ..." >&2

PAGEFILE=$(mktemp)
HEADERS=$(mktemp)
ALLFILE=$(mktemp)
AUTHFILE=$(mktemp)
trap 'rm -f "$PAGEFILE" "$HEADERS" "$ALLFILE" "$AUTHFILE"' EXIT

# Keep the token out of the process list: curl reads the header from a file.
chmod 600 "$AUTHFILE"
printf 'PRIVATE-TOKEN: %s\n' "$GITLAB_TOKEN" > "$AUTHFILE"

page=1
while [ -n "$page" ]; do
  echo "Fetching GitLab page $page ..." >&2

  # No -S/-f: curl's own error text would include the host. Report the status only.
  code=$(curl -s -o "$PAGEFILE" -D "$HEADERS" -w '%{http_code}' \
    --max-time 60 --retry 5 --retry-delay 10 --retry-all-errors \
    -H "@${AUTHFILE}" \
    "${GITLAB_API_URL}/groups/${GROUP_ENC}/merge_requests?state=opened&scope=all&include_subgroups=true&non_archived=true&created_before=${CUTOFF}&per_page=${PER_PAGE}&page=${page}" \
    || true)

  if [ "$code" != "200" ]; then
    echo "GitLab API request failed (HTTP $code) on page $page" >&2
    exit 1
  fi

  # Drafts are filtered here (older GitLab versions expose work_in_progress
  # instead of draft). references.full is "group/project!iid". GitLab list
  # responses carry no approval decision, so it is approximated from
  # detailed_merge_status (GitLab 15.6+).
  jq -c '.[]
    | select((.draft // .work_in_progress // false) | not)
    | {
        number: .iid,
        title: .title,
        url: .web_url,
        createdAt: .created_at,
        author: {login: (.author.username // null)},
        repository: {nameWithOwner: ("gitlab:" + (.references.full | sub("![0-9]+$"; "")))},
        reviewRequests: {nodes: [.reviewers[]? | {requestedReviewer: {login: .username}}]},
        latestReviews: {nodes: []},
        labels: {nodes: [(.labels // [])[] | {name: .}]},
        reviewDecision: (
          if .detailed_merge_status == "requested_changes" then "CHANGES_REQUESTED"
          elif .detailed_merge_status == "not_approved" then "REVIEW_REQUIRED"
          elif .detailed_merge_status == "mergeable" then "APPROVED"
          else null end)
      }' "$PAGEFILE" >> "$ALLFILE"

  page=$(awk -F': *' 'tolower($1) == "x-next-page" { gsub(/\r/, "", $2); print $2 }' "$HEADERS")
done

cp "$ALLFILE" "$OUTPUT"

COUNT=$(wc -l < "$OUTPUT" | tr -d ' ')
echo "Found $COUNT GitLab MRs -> $OUTPUT" >&2
echo "$COUNT"
