# Testing the Stale PR Slack Notification

The workflow [stale-prs-slack.yml](../workflows/stale-prs-slack.yml) runs on a weekday schedule and posts a Slack Block Kit message listing open PRs created more than 3 days ago. The payload logic lives in `build-slack-payload.sh` so it can be tested locally without triggering a workflow run.

## Prerequisites

- [`gh`](https://cli.github.com/) CLI, authenticated (`gh auth login`)
- `jq`
- `python3` with `PyYAML` (`pip install pyyaml`)
- (Optional) A Slack Incoming Webhook URL to test the actual POST

## Step 1 — Generate the ignored-repos list

```bash
python3 -c "
import yaml, json
with open('conf/pds-products.yaml') as f:
    data = yaml.safe_load(f)
repos = [
    'NASA-PDS/' + r
    for p in data['products'].values()
    if p.get('ignore', False)
    for r in p.get('repositories', [])
]
print(json.dumps(repos))
" > ignored_repos.json
```

## Step 2a — Fetch real PR data from GitHub

```bash
CUTOFF=$(date -u -d '3 days ago' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null \
  || date -u -v-3d '+%Y-%m-%dT%H:%M:%SZ')

gh api graphql --paginate -f query='
  query($endCursor: String) {
    search(
      query: "org:NASA-PDS is:pr is:open draft:false created:<'"$CUTOFF"'"
      type: ISSUE
      first: 100
      after: $endCursor
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        ... on PullRequest {
          number title url createdAt
          author { login }
          repository { nameWithOwner }
          assignees(first: 5) { nodes { login } }
          labels(first: 5) { nodes { name } }
          reviewDecision
        }
      }
    }
  }
' --jq '.data.search.nodes[]' > stale_prs.json

echo "Found $(jq -s 'length' stale_prs.json) PRs"
```

## Step 2b — Or use a synthetic fixture

Create `stale_prs.json` with one JSON object per line:

```json
{"number":42,"title":"Fix something","url":"https://github.com/NASA-PDS/validate/pull/42","createdAt":"2026-07-10T12:00:00Z","author":{"login":"jpadams"},"repository":{"nameWithOwner":"NASA-PDS/validate"},"assignees":{"nodes":[{"login":"jpadams"}]},"labels":{"nodes":[{"name":"bug"}]},"reviewDecision":"REVIEW_REQUIRED"}
{"number":3,"title":"Security patch","url":"https://github.com/NASA-PDS/registry/pull/3","createdAt":"2026-07-09T08:00:00Z","author":{"login":"dependabot[bot]"},"repository":{"nameWithOwner":"NASA-PDS/registry"},"assignees":{"nodes":[]},"labels":{"nodes":[{"name":"security"},{"name":"dependencies"}]},"reviewDecision":null}
```

## Step 3 — Build and inspect the payload

```bash
.github/scripts/build-slack-payload.sh stale_prs.json ignored_repos.json | jq .
```

Check which PRs were included:

```bash
.github/scripts/build-slack-payload.sh stale_prs.json ignored_repos.json \
  | jq '[.blocks[] | select(.type == "section") | .text.text]'
```

Check the PR count shown in the header:

```bash
.github/scripts/build-slack-payload.sh stale_prs.json ignored_repos.json \
  | jq '.blocks[] | select(.type == "context") | .elements[0].text' | head -1
```

## Step 4 — (Optional) Send to Slack

```bash
SLACK_WORKFLOW_WEBHOOK_URL="https://hooks.slack.com/services/..."

.github/scripts/build-slack-payload.sh stale_prs.json ignored_repos.json > payload.json

curl -s -f -X POST "$SLACK_WORKFLOW_WEBHOOK_URL" \
  -H 'Content-Type: application/json' \
  -d @payload.json
```

## Triggering the workflow manually

You can also trigger the workflow from the GitHub Actions tab using **Run workflow** on the `main` branch, or via the CLI:

```bash
gh workflow run stale-prs-slack.yml --repo NASA-PDS/.github
```

## Filters applied by the script

| Filter | Behaviour |
|--------|-----------|
| `draft:false` in search query | Draft PRs never returned |
| `created:<CUTOFF` in search query | Only PRs open ≥ 3 days |
| `ignore: true` in `conf/pds-products.yaml` | Repos (e.g. forks, archived, node products) silently dropped |
| `dependabot[bot]` author without `security` label | Routine version-bump PRs dropped; security updates shown |
