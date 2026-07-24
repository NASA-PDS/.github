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
IGNORED=$(cat "$IGNORED_FILE")

jq -s \
  --arg today "$TODAY" \
  --argjson now "$NOW" \
  --argjson ignored "$IGNORED" '
  def days_old(dt):
    ($now - (dt | sub("\\.[0-9]+Z$"; "Z") | strptime("%Y-%m-%dT%H:%M:%SZ") | mktime)) / 86400 | floor;
  def review_label(r):
    if r == "APPROVED" then "✅ Approved"
    elif r == "CHANGES_REQUESTED" then "🔴 Changes Requested"
    elif r == "REVIEW_REQUIRED" then "👀 Review Required"
    else "💬 No Reviews" end;
  def label_str(ls):
    if (ls | length) > 0 then " [" + (ls | join(", ")) + "]" else "" end;
  def assignee_str(a):
    if (a | length) > 0 then a | join(", ") else "unassigned" end;
  # True for Dependabot PRs that are NOT security updates — exclude these
  def is_routine_dependabot:
    .author.login == "dependabot[bot]" and
    (.labels.nodes | map(.name | ascii_downcase) | any(. == "security") | not);
  [.[] |
    select(.repository.nameWithOwner | IN($ignored[]) | not) |
    select(is_routine_dependabot | not)]
  | sort_by(.createdAt) as $sorted
  | ($sorted | length) as $total
  | ($sorted | .[:22]) as $shown
  | {
      "blocks": (
        [
          {"type": "header", "text": {"type": "plain_text", "text": "🌵 Tumbleweeds Report — \($today)", "emoji": true}},
          {"type": "context", "elements": [{"type": "mrkdwn", "text": "\($total) open PR(s) created more than 3 days ago"}]},
          {"type": "divider"}
        ] +
        ($shown | map(. as $pr | [
          {"type": "section", "text": {"type": "mrkdwn",
            "text": "*<\($pr.url)|\($pr.repository.nameWithOwner) #\($pr.number) — \($pr.title)\(label_str($pr.labels.nodes | map(.name)))>*"}},
          {"type": "context", "elements": [{"type": "mrkdwn",
            "text": "\(days_old($pr.createdAt))d old | \(review_label($pr.reviewDecision)) | \(assignee_str($pr.assignees.nodes | map(.login)))"}]}
        ]) | flatten) +
        if $total > 22 then
          [{"type": "section", "text": {"type": "mrkdwn",
            "text": "_...and \($total - 22) more. See <https://github.com/NASA-PDS|NASA-PDS on GitHub>._"}}]
        else [] end
      )
    }
' "$STALE_FILE"
