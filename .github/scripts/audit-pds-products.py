#!/usr/bin/env python3
"""
Audit conf/pds-products.yaml against the live NASA-PDS GitHub org.

Checks two directions:
  - MISSING: repos that exist in the org but are not listed in any product
  - STALE:   repos listed in the config that no longer exist in the org

Repos under products with `ignore: true` are excluded from the MISSING check
(they are intentionally omitted from automation).

Exit codes:
  0  always — discrepancies are logged as GitHub Actions warnings/annotations
              and written to the job summary, but the workflow step does not fail.
              This allows the audit to surface findings without blocking CI.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def load_config(config_path: str) -> dict:
    """Parse pds-products.yaml without external dependencies."""
    products = {}
    current_product = None
    in_products_section = False
    in_repos = False

    with open(config_path) as f:
        for raw_line in f:
            line = raw_line.rstrip('\n')
            stripped = line.lstrip()

            if not stripped or stripped.startswith('#'):
                continue

            indent = len(line) - len(stripped)

            if line == 'products:':
                in_products_section = True
                current_product = None
                in_repos = False
                continue

            if not in_products_section:
                continue

            if indent == 0:
                break

            if indent == 2 and stripped.endswith(':') and not stripped.startswith('-'):
                current_product = stripped[:-1]
                products[current_product] = {'repositories': [], 'ignore': False}
                in_repos = False
                continue

            if current_product is None:
                continue

            if indent == 4:
                in_repos = False
                if stripped.startswith('repositories:'):
                    in_repos = True
                elif stripped.startswith('ignore:'):
                    val = stripped.split(':', 1)[1].strip()
                    products[current_product]['ignore'] = (val == 'true')
                continue

            if indent == 6 and in_repos and stripped.startswith('- '):
                repo = stripped[2:].strip().strip('"\'')
                products[current_product]['repositories'].append(repo)

    return products


def gh_api(args: list) -> str:
    result = subprocess.run(
        ['gh', 'api'] + args,
        capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def list_org_repos(org: str) -> tuple:
    """Return (active_repos, all_repos).

    active_repos — non-archived, non-fork repos; used for the MISSING check so
                   forks and archived repos don't generate spurious "not in config"
                   warnings.
    all_repos    — every repo in the org including forks and archived; used for
                   the STALE check so repos that exist (even as forks) are not
                   falsely flagged as missing from the org.
    """
    active_repos = set()
    all_repos = set()
    page = 1
    while True:
        raw = gh_api([f'orgs/{org}/repos?per_page=100&page={page}'])
        batch = json.loads(raw) if raw else []
        if not batch:
            break
        for r in batch:
            all_repos.add(r['name'])
            if not r.get('archived') and not r.get('fork'):
                active_repos.add(r['name'])
        if len(batch) < 100:
            break
        page += 1
    return active_repos, all_repos


def annotate(level: str, message: str) -> None:
    """Emit a GitHub Actions workflow annotation."""
    print(f"::{level} ::{message}", flush=True)


def write_summary(lines: list) -> None:
    """Append lines to the GitHub Actions job summary if available."""
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if not summary_path:
        return
    with open(summary_path, 'a') as f:
        f.write('\n'.join(lines) + '\n')


def main() -> int:
    config_path = os.environ.get('CONFIG_PATH', 'conf/pds-products.yaml')
    org = os.environ.get('ORG', 'NASA-PDS')

    if not Path(config_path).exists():
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        return 1

    print(f"Loading {config_path} ...")
    products = load_config(config_path)

    config_repos: set = set()
    ignored_repos: set = set()

    for info in products.values():
        for repo in info.get('repositories', []):
            if info.get('ignore'):
                ignored_repos.add(repo)
            else:
                config_repos.add(repo)

    print(f"  {len(config_repos)} repos mapped (non-ignored), {len(ignored_repos)} ignored")

    print(f"\nFetching repos from {org} org ...")
    try:
        active_org_repos, all_org_repos = list_org_repos(org)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: failed to list org repos: {e.stderr}", file=sys.stderr)
        return 1

    print(f"  {len(all_org_repos)} repos found in org ({len(active_org_repos)} active, "
          f"{len(all_org_repos) - len(active_org_repos)} forks/archived)")

    # All repos in config (ignored or not) — used for stale check
    all_config_repos = config_repos | ignored_repos

    # MISSING: active org repos not accounted for in config at all
    missing = sorted(active_org_repos - all_config_repos)
    # STALE: config entries pointing to repos that don't exist in the org (even as forks)
    stale = sorted(all_config_repos - all_org_repos)

    discrepancies = len(missing) + len(stale)

    if discrepancies == 0:
        print("\n✅ pds-products.yaml is in sync with the org — no discrepancies found.")
        write_summary(["## pds-products.yaml Audit", "", "✅ No discrepancies found."])
        return 0

    # ── report ────────────────────────────────────────────────────────────────
    print(f"\n⚠️  Found {discrepancies} discrepancy(ies):\n")

    summary_lines = [
        "## pds-products.yaml Audit",
        "",
        f"Found **{discrepancies}** discrepancy(ies). Update `conf/pds-products.yaml` to resolve.",
        "",
    ]

    if missing:
        print(f"MISSING from pds-products.yaml ({len(missing)} repos in org but not in config):")
        summary_lines += [f"### Missing from config ({len(missing)})", ""]
        for repo in missing:
            msg = f"{org}/{repo} exists in the org but is not listed in pds-products.yaml"
            print(f"  - {repo}")
            annotate("warning", msg)
            summary_lines.append(f"- `{repo}` — exists in org, not in config")
        summary_lines.append("")

    if stale:
        print(f"\nSTALE in pds-products.yaml ({len(stale)} repos in config but not in org):")
        summary_lines += [f"### Stale in config ({len(stale)})", ""]
        for repo in stale:
            msg = f"{org}/{repo} is listed in pds-products.yaml but does not exist in the org"
            print(f"  - {repo}")
            annotate("warning", msg)
            summary_lines.append(f"- `{repo}` — in config, not in org")
        summary_lines.append("")

    write_summary(summary_lines)

    print(f"\nSee job summary and annotations for details.")
    print(f"Update conf/pds-products.yaml to resolve. Resolves: "
          f"https://github.com/NASA-PDS/systems-engineering/issues/172")
    return 0


if __name__ == '__main__':
    sys.exit(main())
