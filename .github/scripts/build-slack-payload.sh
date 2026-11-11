#!/usr/bin/env bash
# Build a Slack Block Kit payload from stale PR data.
#
# Usage:
#   build-slack-payload.sh [stale_prs.json] [ignored_repos.json]
#
# Both args default to files in the current directory.
# Writes the payload JSON to stdout.
#
# Items whose repository name starts with "gitlab:" are GitLab merge requests
# (see fetch-gitlab-mrs.sh); the summary line counts each source separately.
# Optional: GITLAB_MRS_URL adds a "view all" link for GitLab merge requests.
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
GITLAB_MRS_URL="${GITLAB_MRS_URL:-}"

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
  --arg cutoff "$CUTOFF" \
  --arg gitlab_url "$GITLAB_MRS_URL" '
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
  # Slack mrkdwn requires these three characters to be escaped; unescaped, a
  # title such as "Add <foo> & bar" breaks the surrounding link.
  def esc:
    gsub("&"; "&amp;") | gsub("<"; "&lt;") | gsub(">"; "&gt;");
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
  | ($sorted | map(select(.repository.nameWithOwner | startswith("gitlab:"))) | length) as $mrs
  | ($total - $mrs) as $prs
  | (if $mrs == 0 then "\($total) open PR(s) created more than 3 days ago"
     elif $prs == 0 then "\($mrs) open GitLab MR(s) created more than 3 days ago"
     else "\($total) open items created more than 3 days ago (\($prs) GitHub PR(s), \($mrs) GitLab MR(s))"
     end) as $summary
  | ([
      (if $mrs == 0 or $prs > 0 then
        {"type": "mrkdwn", "text": "<https://github.com/pulls?q=is%3Apr+is%3Aopen+org%3ANASA-PDS|View all open NASA-PDS pull requests →>"}
      else empty end),
      (if $mrs > 0 and ($gitlab_url | length) > 0 then
        {"type": "mrkdwn", "text": "<\($gitlab_url)|View all open GitLab merge requests →>"}
      else empty end)
    ]) as $footer
  | {
      "blocks": (
        [
          {"type": "header", "text": {"type": "plain_text", "text": "🌵 Tumbleweeds Report — \($today)", "emoji": true}},
          {"type": "context", "elements": [{"type": "mrkdwn", "text": $summary}]},
          {"type": "divider"}
        ] +
        # One context block per PR: title link on first element, metadata on second.
        # context blocks render compactly with guaranteed link support.
        ($shown | map(. as $pr | {
          "type": "context",
          "elements": [
            {"type": "mrkdwn", "text": "*<\($pr.url)|\($pr.repository.nameWithOwner) #\($pr.number) — \(($pr.title + label_str($pr.labels.nodes | map(.name))) | esc)>*"},
            {"type": "mrkdwn", "text": "\(days_old($pr.createdAt))d old  ·  \(review_label($pr.reviewDecision))  ·  \(reviewer_str(all_reviewers($pr)))"}
          ]
        })) +
        (if $total > 40 then
          [{"type": "context", "elements": [{"type": "mrkdwn",
            "text": "_...and \($total - 40) more not shown._"}]}]
        else [] end) +
        (if ($footer | length) > 0 then
          [{"type": "divider"},
           {"type": "context", "elements": $footer}]
        else [] end)
      )
    }
' "$STALE_FILE"
