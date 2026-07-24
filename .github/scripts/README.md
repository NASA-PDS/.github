# Testing the Stale PR Slack Notification

The workflow [stale-prs-slack.yml](../workflows/stale-prs-slack.yml) runs on a weekday schedule and posts a Slack Block Kit message listing open PRs created more than 3 days ago. The pipeline is split across two scripts so each part can be tested independently.

## Prerequisites

- [`gh`](https://cli.github.com/) CLI, authenticated (`gh auth login`)
- `jq`
- `python3` with `PyYAML` (`pip install pyyaml`)
- (Optional) A Slack Incoming Webhook URL to test the actual POST

## Step 1 — Fetch stale PR data from GitHub

```bash
GH_TOKEN=$(gh auth token) .github/scripts/fetch-stale-prs.sh stale_prs.json
```

This writes one JSON object per line to `stale_prs.json`. Each object includes `reviewRequests` (pending review requests) and `latestReviews` (already-submitted reviews) so both sets of reviewers appear in the report.

### Or use a synthetic fixture

Create `stale_prs.json` with one JSON object per line:

```json
{"number":42,"title":"Fix something","url":"https://github.com/NASA-PDS/validate/pull/42","createdAt":"2026-07-10T12:00:00Z","author":{"login":"jpadams"},"repository":{"nameWithOwner":"NASA-PDS/validate"},"reviewRequests":{"nodes":[{"requestedReviewer":{"login":"anilnatha"}}]},"latestReviews":{"nodes":[]},"labels":{"nodes":[{"name":"bug"}]},"reviewDecision":"REVIEW_REQUIRED"}
{"number":3,"title":"Security patch","url":"https://github.com/NASA-PDS/registry/pull/3","createdAt":"2026-07-09T08:00:00Z","author":{"login":"dependabot"},"repository":{"nameWithOwner":"NASA-PDS/registry"},"reviewRequests":{"nodes":[]},"latestReviews":{"nodes":[{"author":{"login":"jordanpadams"},"state":"APPROVED"}]},"labels":{"nodes":[{"name":"security"},{"name":"dependencies"}]},"reviewDecision":null}
```

## Step 2 — Generate the ignored-repos list

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

## Step 3 — Build and inspect the payload

```bash
.github/scripts/build-slack-payload.sh stale_prs.json ignored_repos.json | jq .
```

Check which PRs were included and their reviewer/status lines:

```bash
.github/scripts/build-slack-payload.sh stale_prs.json ignored_repos.json \
  | jq '.blocks[] | select(.type == "context") | .elements'
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

```bash
gh workflow run stale-prs-slack.yml --repo NASA-PDS/.github
```

Or use the **Run workflow** button on the Actions tab.

## Filters applied by the script

| Filter | Behaviour |
|--------|-----------|
| `draft:false` in search query | Draft PRs never returned |
| `created:<CUTOFF` in search query | Only PRs open ≥ 3 days |
| `ignore: true` in `conf/pds-products.yaml` | Repos (e.g. forks, archived, node products) silently dropped |
| `dependabot` author without `security` label | Routine version-bump PRs dropped; security updates shown when `INCLUDE_DEPENDABOT=true` |

## Slack App setup

The notification is sent via a Slack Incoming Webhook. The webhook URL is stored in the `SLACK_WORKFLOW_WEBHOOK_URL` GitHub Actions secret.

**Incoming Webhooks are permanently bound to the channel chosen at creation.** To change the target channel:

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **PDS Tumbleweeds App** → **Incoming Webhooks**
2. Click **Add New Webhook to Workspace** and select the new channel
3. Copy the new webhook URL
4. Update the `SLACK_WORKFLOW_WEBHOOK_URL` secret at **github.com/NASA-PDS/.github → Settings → Secrets and variables → Actions**

### Creating the app from scratch

1. [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. Name: `PDS Tumbleweeds App` — select the NASA-PDS workspace
3. **Features** → **Incoming Webhooks** → toggle on → **Add New Webhook to Workspace**
4. Select the target channel → **Allow** → copy the webhook URL
5. Add the URL as the `SLACK_WORKFLOW_WEBHOOK_URL` secret in GitHub Actions
