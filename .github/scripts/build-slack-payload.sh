#!/usr/bin/env bash
# Build a Slack Block Kit payload from stale PR data.
#
# Usage:
#   build-slack-payload.sh [stale_prs.json] [ignored_repos.json]
#
# Both args default to files in the current directory.
# Writes the payload JSON to stdout.
#
# Local test example:
#   gh api graphql ... --jq '.data.search.nodes[]' > stale_prs.json
#   python3 .github/scripts/extract-ignored-repos.py > ignored_repos.json
#   .github/scripts/build-slack-payload.sh | jq .
set -euo pipefail

STALE_FILE="${1:-stale_prs.json}"
IGNORED_FILE="${2:-ignored_repos.json}"

if [[ ! -f "$STALE_FILE" ]]; then
  echo "Error: stale PRs file not found: $STALE_FILE" >&2
  exit 1
fi

if [[ ! -f "$IGNORED_FILE" ]]; then
  echo "Error: ignored repos file not found: $IGNORED_FILE" >&2
  exit 1
fi

TODAY=$(date -u '+%Y-%m-%d')
NOW=$(date -u '+%s')
CUTOFF=$(date -u -d '3 days ago' '+%Y-%m-%d' 2>/dev/null || date -u -v-3d '+%Y-%m-%d')
IGNORED=$(cat "$IGNORED_FILE")

# When INCLUDE_DEPENDABOT=true, show security-labeled Dependabot PRs.
# When false (default), suppress all Dependabot PRs.
if [[ "${INCLUDE_DEPENDABOT:-false}" == "true" ]]; then
  INCL_DEP=true
else
  INCL_DEP=false
fi

jq -s \
  --arg today "$TODAY" \
  --argjson now "$NOW" \
  --argjson ignored "$IGNORED" \
  --argjson include_dep "$INCL_DEP" \
  --arg cutoff "$CUTOFF" '
  def days_old(dt):
    ($now - (dt | sub("\\.[0-9]+Z$"; "Z") | strptime("%Y-%m-%dT%H:%M:%SZ") | mktime)) / 86400 | floor;
  def review_label(r):
    if r == "APPROVED" then "✅ Approved"
    elif r == "CHANGES_REQUESTED" then "🔴 Changes Requested"
    elif r == "REVIEW_REQUIRED" then "👀 Review Required"
    else "💬 No Reviews" end;
  def label_str(ls):
    if (ls | length) > 0 then " [" + (ls | join(", ")) + "]" else "" end;
  def reviewer_str(a):
    if (a | length) > 0 then a | join(", ") else "no reviewers" end;
  def all_reviewers(pr):
    ((pr.reviewRequests.nodes | map(.requestedReviewer.login) | map(select(. != null))) +
     (pr.latestReviews.nodes | map(.author.login) | map(select(. != null))))
    | unique;
  # Exclude Dependabot PRs (GraphQL returns login as "dependabot", not "dependabot[bot]"):
  #   include_dep=false → drop all Dependabot PRs
  #   include_dep=true  → keep only those labeled "security"
  def is_excluded_dependabot:
    (.author.login == "dependabot" or .author.login == "dependabot[bot]") and
    (if $include_dep then
      (.labels.nodes | map(.name | ascii_downcase) | any(. == "security") | not)
    else
      true
    end);
  [.[] |
    select(.repository.nameWithOwner | IN($ignored[]) | not) |
    select(is_excluded_dependabot | not)]
  | sort_by(.createdAt) as $sorted
  | ($sorted | length) as $total
  | ($sorted | .[:40]) as $shown
  | {
      "blocks": (
        [
          {"type": "header", "text": {"type": "plain_text", "text": "🌵 Tumbleweeds Report — \($today)", "emoji": true}},
          {"type": "context", "elements": [{"type": "mrkdwn", "text": "\($total) open PR(s) created more than 3 days ago"}]},
          {"type": "divider"}
        ] +
        # One context block per PR: title link on first element, metadata on second.
        # context blocks render compactly with guaranteed link support.
        ($shown | map(. as $pr | {
          "type": "context",
          "elements": [
            {"type": "mrkdwn", "text": "*<\($pr.url)|\($pr.repository.nameWithOwner) #\($pr.number) — \($pr.title)\(label_str($pr.labels.nodes | map(.name)))>*"},
            {"type": "mrkdwn", "text": "\(days_old($pr.createdAt))d old  ·  \(review_label($pr.reviewDecision))  ·  \(reviewer_str(all_reviewers($pr)))"}
          ]
        })) +
        (if $total > 40 then
          [{"type": "context", "elements": [{"type": "mrkdwn",
            "text": "_...and \($total - 40) more not shown._"}]}]
        else [] end) +
        [{"type": "divider"},
         {"type": "context", "elements": [{"type": "mrkdwn",
          "text": "<https://github.com/pulls?q=is%3Apr+is%3Aopen+org%3ANASA-PDS|View all open NASA-PDS pull requests →>"}]}]
      )
    }
' "$STALE_FILE"
