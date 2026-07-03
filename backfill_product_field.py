#!/usr/bin/env python3
"""
Backfill the Product field (org-level and project-level) for all open issues across NASA-PDS.

Reads conf/pds-products.yaml to determine which product each repository belongs to.
For each issue:
  - Sets the org-level 'Product' issue field
  - Sets the 'Product' single-select field on every project the issue already belongs to
Interactively prompts for action when a repository isn't in the config.

Usage:
    python3 backfill_product_field.py [--dry-run] [--force] [--repo REPO]

Options:
    --dry-run       Preview what would be done without making any changes.
    --force         Set the field even if it is already populated (default: skip).
    --repo REPO     Process only this repository (e.g. "validate"). Skips org repo listing.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).parent / '.github' / 'scripts'))
from project_automation import GitHubProjectAutomation, GitHubAPIError

ORG = 'NASA-PDS'
CONFIG_PATH = str(Path(__file__).parent / 'conf' / 'pds-products.yaml')
FIELD_NAME = 'Product'


# ── helpers ──────────────────────────────────────────────────────────────────

def gh_json(args: list) -> any:
    result = subprocess.run(
        ['gh'] + args, capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def list_org_repos(org: str) -> List[dict]:
    """Return all non-archived, non-fork repos in the org."""
    data = gh_json(['api', f'orgs/{org}/repos?per_page=100', '--paginate'])
    return [r for r in data if not r.get('archived') and not r.get('fork')]


def list_open_issues(repo_full: str) -> List[dict]:
    """Return all open issues (excluding pull requests) in a repo."""
    data = gh_json(['api', f'repos/{repo_full}/issues?state=open&per_page=100', '--paginate'])
    return [i for i in data if 'pull_request' not in i]


def get_issue_product_value(repo_full: str, issue_number: int, field_id: int) -> Optional[str]:
    """Return the current org-level Product field value on an issue, or None if unset."""
    try:
        data = gh_json(['api', f'repos/{repo_full}/issues/{issue_number}/issue-field-values'])
        for entry in data:
            if entry.get('issue_field_id') == field_id:
                opt = entry.get('single_select_option') or {}
                return opt.get('name')
        return None
    except subprocess.CalledProcessError:
        return None


def get_projects_for_issue(automation: GitHubProjectAutomation, issue_node_id: str, org: str) -> List[Tuple[str, str]]:
    """Return (project_id, item_id) pairs for every project this issue belongs to."""
    query = """
    query($id: ID!) {
        node(id: $id) {
            ... on Issue {
                projectItems(first: 20) {
                    nodes {
                        id
                        project { id }
                    }
                }
            }
        }
    }
    """
    try:
        result = automation._run_gh_api([
            "graphql",
            "-f", f"query={query}",
            "-f", f"id={issue_node_id}",
            "--jq", '.data.node.projectItems.nodes[] | [.project.id, .id] | @tsv'
        ])
        memberships = []
        for line in result.splitlines():
            if line.strip():
                parts = line.split('\t')
                if len(parts) == 2:
                    memberships.append((parts[0], parts[1]))
        return memberships
    except GitHubAPIError:
        return []


def prompt_unknown_repo(repo_name: str, available_products: List[str]) -> Optional[str]:
    """Interactively ask what to do with a repo that isn't in pds-products.yaml.

    Returns the chosen product name, or None to skip.
    Exits the process if the user chooses 'q'.
    """
    sorted_products = sorted(available_products)
    print(f"\n  ⚠️  '{repo_name}' is not in pds-products.yaml")
    print("       [s] Skip this repo  (default)")
    print("       [a] Assign to a product")
    print("       [q] Quit")

    while True:
        raw = input("       Choice [s]: ").strip().lower() or 's'
        if raw == 'q':
            print("Quitting.")
            sys.exit(0)
        if raw == 's':
            return None
        if raw == 'a':
            print("\n       Available products:")
            for i, p in enumerate(sorted_products, 1):
                print(f"         {i:2}. {p}")
            while True:
                val = input("       Product name or number: ").strip()
                if val.isdigit():
                    idx = int(val) - 1
                    if 0 <= idx < len(sorted_products):
                        return sorted_products[idx]
                    print("       Invalid number, try again.")
                elif val in sorted_products:
                    return val
                else:
                    print(f"       '{val}' not recognised, try again.")
        else:
            print("       Please enter 's', 'a', or 'q'.")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Backfill the org-level Product issue field across NASA-PDS"
    )
    parser.add_argument('--dry-run', action='store_true',
                        help="Preview without making changes")
    parser.add_argument('--force', action='store_true',
                        help="Set the field even when it is already populated")
    parser.add_argument('--repo',
                        help="Process only this repo name (e.g. 'validate'); skips org-wide listing")
    args = parser.parse_args()

    automation = GitHubProjectAutomation()

    # ── 1. Load product config ───────────────────────────────────────────────
    print(f"Loading {CONFIG_PATH} ...")
    products = GitHubProjectAutomation._load_products_config(CONFIG_PATH)

    repo_to_product: Dict[str, str] = {}
    ignored_repos: Set[str] = set()
    available_products: List[str] = []

    for product_key, info in products.items():
        product_name = info.get('github_project_name') or product_key
        if info.get('ignore'):
            for repo in info.get('repositories', []):
                ignored_repos.add(repo)
        else:
            available_products.append(product_name)
            for repo in info.get('repositories', []):
                repo_to_product[repo] = product_name

    print(f"  {len(repo_to_product)} repos mapped across {len(set(repo_to_product.values()))} products")
    print(f"  {len(ignored_repos)} repos in ignored products")
    print()

    # ── 2. Fetch the org Product field ──────────────────────────────────────
    print(f"Fetching org '{FIELD_NAME}' issue field ...")
    try:
        field_data = automation.get_org_issue_field(ORG, FIELD_NAME)
    except GitHubAPIError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if not field_data:
        print(f"❌ No '{FIELD_NAME}' field found in {ORG} org issue fields")
        sys.exit(1)

    field_id: int = field_data['id']
    valid_options: Set[str] = {o['name'] for o in field_data.get('options', [])}
    print(f"  Field id {field_id}, {len(valid_options)} options")
    print()

    # ── 3. Build repo list ───────────────────────────────────────────────────
    if args.repo:
        print(f"Single-repo mode: {ORG}/{args.repo}")
        if args.repo in ignored_repos:
            print(f"  ℹ️  '{args.repo}' is in an ignored product — nothing to do")
            sys.exit(0)
        if args.repo not in repo_to_product:
            print(f"  ⚠️  '{args.repo}' is not mapped in pds-products.yaml")
            product = prompt_unknown_repo(args.repo, available_products)
            if product:
                repo_to_product[args.repo] = product
                print(f"       → Assigned '{product}'")
            else:
                print("       → Skipping")
                sys.exit(0)
        all_repos = [{'name': args.repo}]
        print()
    else:
        print(f"Listing repos in {ORG} (non-archived, non-fork) ...")
        try:
            all_repos = list_org_repos(ORG)
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to list repos: {e.stderr}")
            sys.exit(1)
        print(f"  Found {len(all_repos)} repos")
        print()

        # ── 4. Resolve unknown repos interactively ───────────────────────────
        unknown = [
            r['name'] for r in all_repos
            if r['name'] not in repo_to_product and r['name'] not in ignored_repos
        ]

        if unknown:
            print(f"Found {len(unknown)} repo(s) not in pds-products.yaml — please advise:")
            for repo_name in unknown:
                product = prompt_unknown_repo(repo_name, available_products)
                if product:
                    repo_to_product[repo_name] = product
                    print(f"       → Assigned '{product}'")
                else:
                    ignored_repos.add(repo_name)
                    print(f"       → Skipping")
            print()

    # ── 5. Process each mapped repo ──────────────────────────────────────────
    repos_to_process = [r for r in all_repos if r['name'] in repo_to_product]

    dry = "[DRY RUN] " if args.dry_run else ""
    print(f"{dry}Processing {len(repos_to_process)} repos ...\n")

    total_issues = total_set = total_skipped = total_failed = 0

    for repo_info in repos_to_process:
        repo_name = repo_info['name']
        repo_full = f"{ORG}/{repo_name}"
        product_name = repo_to_product[repo_name]

        if product_name not in valid_options:
            print(f"  ⚠️  {repo_full}: '{product_name}' not a valid Product option — skipping repo")
            continue

        try:
            issues = list_open_issues(repo_full)
        except subprocess.CalledProcessError as e:
            print(f"  ❌ {repo_full}: could not list issues ({e.stderr.strip()})")
            continue

        if not issues:
            continue

        total_issues += len(issues)
        repo_set = repo_skipped = repo_failed = 0

        print(f"  {repo_full} ({len(issues)} open) → '{product_name}'")

        for issue in issues:
            num = issue['number']
            issue_node_id = issue.get('node_id')

            if args.dry_run:
                repo_set += 1
                continue

            if not args.force:
                current = get_issue_product_value(repo_full, num, field_id)
                if current is not None:
                    repo_skipped += 1
                    continue

            failed = False

            # Set org-level field
            try:
                automation.set_org_issue_field_value(repo_full, num, field_id, product_name)
            except GitHubAPIError as e:
                print(f"    ❌ #{num} (org field): {e}")
                failed = True

            # Set project-level field on every project this issue is already in
            if issue_node_id:
                memberships = get_projects_for_issue(automation, issue_node_id, ORG)
                for project_id, item_id in memberships:
                    try:
                        automation._set_project_product_field_on_item(
                            project_id, item_id, repo_name, CONFIG_PATH, FIELD_NAME
                        )
                    except GitHubAPIError as e:
                        print(f"    ⚠️  #{num} (project field): {e}")

            if failed:
                repo_failed += 1
            else:
                repo_set += 1

        summary_parts = []
        if repo_set:
            summary_parts.append(f"✅ {repo_set} set")
        if repo_skipped:
            summary_parts.append(f"⏭  {repo_skipped} already set")
        if repo_failed:
            summary_parts.append(f"❌ {repo_failed} failed")
        print(f"    {', '.join(summary_parts)}")

        total_set += repo_set
        total_skipped += repo_skipped
        total_failed += repo_failed

    print()
    print(f"{dry}Done!")
    print(f"  {total_issues} open issues across {len(repos_to_process)} repos")
    if not args.dry_run:
        print(f"  ✅ {total_set} set, ⏭  {total_skipped} already set, ❌ {total_failed} failed")
    else:
        print(f"  Would set {total_set} issues")


if __name__ == '__main__':
    main()
