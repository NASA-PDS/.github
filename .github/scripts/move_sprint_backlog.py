#!/usr/bin/env python3
"""
Find all open NASA-PDS issues with label:<OLD_BUILD> AND label:sprint-backlog
and add label:<NEW_BUILD> to each. The sprint-backlog label is left in place so
the existing label-to-project automation picks them up for the new build sprint.

Usage:
    python3 move_sprint_backlog.py --from B18 --to B19 [--dry-run]
"""

import argparse
import json
import subprocess
import sys


def run_gh(args, check=True):
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True, text=True, check=check
    )
    return result.stdout.strip()


def run_graphql(query, variables=None, jq_filter=None):
    args = ["api", "graphql", "-f", f"query={query}"]
    if variables:
        for k, v in variables.items():
            args += ["-f", f"{k}={v}"]
    if jq_filter:
        args += ["--jq", jq_filter]
    return run_gh(args)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="old_build", required=True, metavar="OLD_BUILD",
                        help="Source build label (e.g. B18)")
    parser.add_argument("--to", dest="new_build", required=True, metavar="NEW_BUILD",
                        help="Target build label (e.g. B19)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without making any changes")
    return parser.parse_args()


def main():
    args = parse_args()
    old_label = args.old_build
    new_label = args.new_build
    dry_run = args.dry_run

    if dry_run:
        print(f"[DRY RUN] No labels will be applied.\n")

    print(f"Searching for open issues with label:{old_label} AND label:sprint-backlog in NASA-PDS...")

    search_query = """
query($cursor: String, $queryStr: String!) {
  search(
    query: $queryStr
    type: ISSUE
    first: 100
    after: $cursor
  ) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Issue {
        id
        number
        title
        url
        repository { nameWithOwner }
        labels(first: 20) {
          nodes { name }
        }
      }
    }
  }
}
"""

    query_str = f"org:NASA-PDS is:issue is:open label:{old_label} label:sprint-backlog"
    all_issues = []
    cursor = None
    while True:
        variables = {"queryStr": query_str}
        if cursor:
            variables["cursor"] = cursor
        raw = run_graphql(search_query, variables)
        data = json.loads(raw)
        search_data = data["data"]["search"]
        all_issues.extend(search_data["nodes"])
        if search_data["pageInfo"]["hasNextPage"]:
            cursor = search_data["pageInfo"]["endCursor"]
        else:
            break

    print(f"  Found {len(all_issues)} open issue(s) with {old_label} + sprint-backlog")

    already_labeled = [i for i in all_issues if any(l["name"] == new_label for l in i["labels"]["nodes"])]
    to_label = [i for i in all_issues if not any(l["name"] == new_label for l in i["labels"]["nodes"])]

    if already_labeled:
        print(f"  {len(already_labeled)} already have {new_label} — skipping")
    print(f"  {len(to_label)} will receive the {new_label} label")
    print()

    if not to_label:
        print("Nothing to do.")
        return

    success = 0
    failed = 0
    print(f"── Applying label {new_label} ──────────────────────────────────────────────")
    for issue in to_label:
        repo = issue["repository"]["nameWithOwner"]
        number = issue["number"]
        print(f"  {'[DRY RUN] ' if dry_run else ''}{repo}#{number}: {issue['title']}")
        if dry_run:
            success += 1
            continue
        try:
            run_gh(["issue", "edit", str(number), "--repo", repo, "--add-label", new_label])
            print(f"    ✅ Labeled {new_label}")
            success += 1
        except subprocess.CalledProcessError as e:
            print(f"    ❌ Failed: {e.stderr.strip()}")
            failed += 1

    print()
    action = "would be labeled" if dry_run else "labeled"
    print(f"Done! {success} issue(s) {action} with {new_label}" +
          (f", {failed} failed" if failed else "") + ".")


if __name__ == "__main__":
    main()
