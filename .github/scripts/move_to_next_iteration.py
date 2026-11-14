#!/usr/bin/env python3
"""
Move GitHub Projects V2 items from one iteration to another.

Selects every item of an organization (or user) project whose iteration field is
set to the source iteration (default: the most recently completed iteration)
and whose Status passes the status filter, then sets the iteration field of
each selected item to the target iteration (default: the current iteration).

Iterations come from the project's iteration field configuration, which GitHub
splits by date (start date + duration) into `iterations` (current and upcoming,
earliest first) and `completedIterations` (most recent first):
  last    = most recently completed iteration
  current = earliest iteration that is not completed
  next    = the iteration after `current`

Status filter: when --excluded-statuses is given, items whose Status is in that
list are left alone (it takes precedence). Otherwise only items whose Status is
in --statuses are moved.

Only `gh api graphql` is used. The token is read by `gh` from the GH_TOKEN
environment variable and never appears on a command line. In --dry-run mode no
mutation is sent: any mutation attempt raises before reaching the API.

Every option can also be set from an environment variable (shown in --help),
which is how the workflow passes its inputs.

Usage:
    GH_TOKEN=... python3 move_to_next_iteration.py \\
        --owner NASA-PDS --number 34 --iteration-field sprint \\
        --excluded-statuses Done --dry-run

Exit status: 0 on success, 1 on any API/configuration error or failed move,
2 on invalid usage.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
FROM_CHOICES = ("last", "current")
TO_CHOICES = ("current", "next")
ITERATION_VALUE = "ProjectV2ItemFieldIterationValue"
SINGLE_SELECT_VALUE = "ProjectV2ItemFieldSingleSelectValue"

PROJECT_QUERY = """
query($owner: String!, $number: Int!) {
  repositoryOwner(login: $owner) {
    ... on ProjectV2Owner {
      projectV2(number: $number) {
        id
        fields(first: 100) {
          pageInfo { hasNextPage }
          nodes {
            ... on ProjectV2FieldCommon { id name dataType }
            ... on ProjectV2IterationField {
              configuration {
                iterations { id title startDate duration }
                completedIterations { id title startDate duration }
              }
            }
          }
        }
      }
    }
  }
}
"""

ITEMS_QUERY = """
query($owner: String!, $number: Int!, $after: String) {
  repositoryOwner(login: $owner) {
    ... on ProjectV2Owner {
      projectV2(number: $number) {
        items(first: 100, after: $after) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            type
            isArchived
            content {
              __typename
              ... on Issue { number title repository { nameWithOwner isPrivate } }
              ... on PullRequest { number title repository { nameWithOwner isPrivate } }
              ... on DraftIssue { title }
            }
            fieldValues(first: 100) {
              pageInfo { hasNextPage }
              nodes {
                __typename
                ... on ProjectV2ItemFieldIterationValue {
                  iterationId
                  field { ... on ProjectV2FieldCommon { id } }
                }
                ... on ProjectV2ItemFieldSingleSelectValue {
                  name
                  field { ... on ProjectV2FieldCommon { id } }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

UPDATE_MUTATION = """
mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $iterationId: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $projectId,
    itemId: $itemId,
    fieldId: $fieldId,
    value: {iterationId: $iterationId}
  }) {
    projectV2Item { id }
  }
}
"""

GraphQL = Callable[[str, Dict[str, Any]], Dict[str, Any]]


class ProjectIterationError(Exception):
    """Base class for errors raised by this script."""


class GraphQLError(ProjectIterationError):
    """A `gh api graphql` call failed or returned errors."""


class ProjectConfigError(ProjectIterationError):
    """The project does not have what the requested move needs."""


@dataclass
class Item:
    """The parts of a project item this script needs."""

    id: str
    iteration_id: Optional[str]
    status: Optional[str]
    kind: str = "UNKNOWN"
    is_archived: bool = False
    repository: Optional[str] = None
    is_private: bool = True
    number: Optional[int] = None
    title: Optional[str] = None

    def label(self, show_titles: bool = False) -> str:
        """Describe the item without leaking private details by default."""
        if self.repository and self.number is not None and not self.is_private:
            text = f"{self.repository}#{self.number}"
        else:
            text = "private or draft item"
        if show_titles and self.title:
            text += f" - {self.title}"
        return f"{self.id} ({text})"


@dataclass
class Selection:
    """Result of applying the iteration and status filters to the items."""

    in_source: List[Item] = field(default_factory=list)
    to_move: List[Item] = field(default_factory=list)
    skipped_by_status: List[Item] = field(default_factory=list)


# --------------------------------------------------------------------------
# GraphQL transport
# --------------------------------------------------------------------------

def run_graphql(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    """Run one GraphQL document through `gh api graphql` and return `data`.

    Arguments are passed as a list (no shell). Integer variables use `-F`
    (typed), everything else uses `-f` (literal string, never read from a file).
    """
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is None:
            continue
        flag = "-F" if isinstance(value, int) and not isinstance(value, bool) else "-f"
        cmd += [flag, f"{key}={value}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        raise GraphQLError(f"Could not run gh: {e}") from e
    if result.returncode != 0:
        detail = (result.stderr.strip() or result.stdout.strip())[:1000]
        raise GraphQLError(f"gh api graphql failed (exit {result.returncode}): {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise GraphQLError(f"Invalid JSON from gh api graphql: {e}") from e
    if payload.get("errors"):
        messages = "; ".join(str(err.get("message", err)) for err in payload["errors"])
        raise GraphQLError(f"GraphQL errors: {messages[:1000]}")
    data = payload.get("data")
    if data is None:
        raise GraphQLError("GraphQL response has no data")
    return data


def read_only(graphql: GraphQL) -> GraphQL:
    """Wrap a GraphQL runner so mutations are refused (used for --dry-run)."""

    def guarded(query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        if query.lstrip().startswith("mutation"):
            raise ProjectIterationError("Refusing to run a mutation in dry-run mode")
        return graphql(query, variables)

    return guarded


# --------------------------------------------------------------------------
# Project lookup and iteration resolution
# --------------------------------------------------------------------------

def load_project(graphql: GraphQL, owner: str, number: int) -> Dict[str, Any]:
    """Return the project node (id and fields) or raise if it is not visible."""
    data = graphql(PROJECT_QUERY, {"owner": owner, "number": number})
    owner_node = data.get("repositoryOwner") or {}
    project = owner_node.get("projectV2")
    if not project:
        raise ProjectConfigError(
            f"Project {owner}#{number} not found or not readable with this token"
        )
    if project["fields"]["pageInfo"]["hasNextPage"]:
        raise ProjectConfigError("Project has more than 100 fields; not supported")
    return project


def find_field(fields: List[Dict[str, Any]], name: str, data_type: str) -> Dict[str, Any]:
    """Find a project field by name (case-insensitive) and check its type."""
    wanted = name.strip().lower()
    for node in fields:
        if (node.get("name") or "").lower() == wanted:
            if node.get("dataType") != data_type:
                raise ProjectConfigError(
                    f'Field "{node.get("name")}" is {node.get("dataType")}, expected {data_type}'
                )
            return node
    raise ProjectConfigError(f'No {data_type} field named "{name}" found in the project')


def pick_iterations(configuration: Dict[str, Any]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Return the last, current and next iterations from a field configuration.

    `completedIterations` is ordered most recent first and `iterations` earliest
    first by the API; both are sorted by start date here so the result does not
    depend on that ordering.
    """
    completed = sorted(
        configuration.get("completedIterations") or [],
        key=lambda it: it["startDate"],
        reverse=True,
    )
    upcoming = sorted(configuration.get("iterations") or [], key=lambda it: it["startDate"])
    return {
        "last": completed[0] if completed else None,
        "current": upcoming[0] if upcoming else None,
        "next": upcoming[1] if len(upcoming) > 1 else None,
    }


def resolve_iterations(
    configuration: Dict[str, Any], from_kind: str, to_kind: str
) -> Dict[str, Dict[str, Any]]:
    """Return {"from": iteration, "to": iteration} or raise if one is missing."""
    picked = pick_iterations(configuration)
    source = picked[from_kind]
    if not source:
        raise ProjectConfigError(f"No {from_kind} iteration found. Check if the iteration exists.")
    target = picked[to_kind]
    if not target:
        raise ProjectConfigError(f"No {to_kind} iteration found. Check if the iteration exists.")
    return {"from": source, "to": target}


# --------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------

def parse_item(node: Dict[str, Any], iteration_field_id: str, status_field_id: str) -> Item:
    """Convert an items GraphQL node into an Item."""
    values = node["fieldValues"]
    if values["pageInfo"]["hasNextPage"]:
        raise ProjectConfigError(f"Item {node['id']} has more than 100 field values; not supported")
    iteration_id = None
    status = None
    for value in values["nodes"]:
        value_field = (value.get("field") or {}).get("id")
        kind = value.get("__typename")
        if kind == ITERATION_VALUE and value_field == iteration_field_id:
            iteration_id = value.get("iterationId")
        elif kind == SINGLE_SELECT_VALUE and value_field == status_field_id:
            status = value.get("name")
    content = node.get("content") or {}
    repo = content.get("repository") or {}
    return Item(
        id=node["id"],
        iteration_id=iteration_id,
        status=status,
        kind=node.get("type") or "UNKNOWN",
        is_archived=bool(node.get("isArchived")),
        repository=repo.get("nameWithOwner"),
        is_private=bool(repo.get("isPrivate", True)),
        number=content.get("number"),
        title=content.get("title"),
    )


def fetch_items(
    graphql: GraphQL, owner: str, number: int, iteration_field_id: str, status_field_id: str
) -> List[Item]:
    """Fetch every item of the project, following pagination cursors."""
    items: List[Item] = []
    cursor: Optional[str] = None
    while True:
        data = graphql(ITEMS_QUERY, {"owner": owner, "number": number, "after": cursor})
        project = (data.get("repositoryOwner") or {}).get("projectV2")
        if not project:
            raise ProjectConfigError(f"Project {owner}#{number} not found or not readable")
        page = project["items"]
        items.extend(
            parse_item(node, iteration_field_id, status_field_id) for node in page["nodes"]
        )
        if not page["pageInfo"]["hasNextPage"]:
            return items
        cursor = page["pageInfo"]["endCursor"]


def parse_list(value: Optional[str]) -> List[str]:
    """Split a comma-separated list, trimming blanks and dropping empty entries."""
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def status_allowed(status: Optional[str], excluded: List[str], statuses: List[str]) -> bool:
    """Apply the status filter. Excluded statuses take precedence over statuses."""
    if excluded:
        return status not in excluded
    return status in statuses


def select_items(
    items: List[Item], source_iteration_id: str, excluded: List[str], statuses: List[str]
) -> Selection:
    """Select the items to move: in the source iteration and passing the status filter."""
    selection = Selection()
    for item in items:
        if item.iteration_id != source_iteration_id:
            continue
        selection.in_source.append(item)
        if status_allowed(item.status, excluded, statuses):
            selection.to_move.append(item)
        else:
            selection.skipped_by_status.append(item)
    return selection


def move_item(
    graphql: GraphQL, project_id: str, field_id: str, item: Item, iteration_id: str
) -> None:
    """Set the iteration field of one item."""
    graphql(
        UPDATE_MUTATION,
        {
            "projectId": project_id,
            "itemId": item.id,
            "fieldId": field_id,
            "iterationId": iteration_id,
        },
    )


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--owner", default=os.environ.get("PROJECT_OWNER"),
                        help="Organization or user that owns the project [PROJECT_OWNER]")
    parser.add_argument("--number", type=int, default=os.environ.get("PROJECT_NUMBER"),
                        help="Project number as shown in its URL [PROJECT_NUMBER]")
    parser.add_argument("--iteration-field", default=os.environ.get("ITERATION_FIELD"),
                        help="Name of the iteration field, case-insensitive [ITERATION_FIELD]")
    parser.add_argument("--status-field", default=os.environ.get("STATUS_FIELD", "Status"),
                        help="Name of the single-select status field (default: Status) [STATUS_FIELD]")
    parser.add_argument("--from-iteration", choices=FROM_CHOICES,
                        default=os.environ.get("FROM_ITERATION", "last"),
                        help="Iteration to move items out of (default: last) [FROM_ITERATION]")
    parser.add_argument("--to-iteration", choices=TO_CHOICES,
                        default=os.environ.get("TO_ITERATION", "current"),
                        help="Iteration to move items into (default: current) [TO_ITERATION]")
    parser.add_argument("--excluded-statuses", default=os.environ.get("EXCLUDED_STATUSES", ""),
                        help="Comma-separated statuses that must not be moved; takes "
                             "precedence over --statuses [EXCLUDED_STATUSES]")
    parser.add_argument("--statuses", default=os.environ.get("STATUSES", ""),
                        help="Comma-separated statuses to move when no excluded statuses "
                             "are given [STATUSES]")
    parser.add_argument("--dry-run", action="store_true", default=env_flag("DRY_RUN"),
                        help="Print what would move and send no mutation [DRY_RUN=true]")
    parser.add_argument("--show-titles", action="store_true",
                        help="Include issue titles in the item list (do not use in public logs)")
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.owner or not OWNER_RE.match(args.owner):
        parser.error("--owner (or PROJECT_OWNER) is required and must be a GitHub login")
    if args.number is None or args.number < 1:
        parser.error("--number (or PROJECT_NUMBER) is required and must be a positive integer")
    if not args.iteration_field or not args.iteration_field.strip():
        parser.error("--iteration-field (or ITERATION_FIELD) is required")
    if not parse_list(args.excluded_statuses) and not parse_list(args.statuses):
        parser.error("give --excluded-statuses or --statuses (or the matching environment variable)")
    if os.environ.get("GITHUB_ACTIONS") == "true" and not os.environ.get("GH_TOKEN"):
        parser.error("GH_TOKEN is empty; check that the secret exists")


def run(args: argparse.Namespace, graphql: GraphQL) -> int:
    """Perform the move. Returns the process exit status."""
    excluded = parse_list(args.excluded_statuses)
    statuses = parse_list(args.statuses)
    if args.dry_run:
        graphql = read_only(graphql)
        print("[DRY RUN] No item will be changed.")

    project = load_project(graphql, args.owner, args.number)
    iteration_field = find_field(project["fields"]["nodes"], args.iteration_field, "ITERATION")
    status_field = find_field(project["fields"]["nodes"], args.status_field, "SINGLE_SELECT")
    iterations = resolve_iterations(
        iteration_field["configuration"], args.from_iteration, args.to_iteration
    )
    source, target = iterations["from"], iterations["to"]

    print(f"Project: {args.owner}#{args.number}, field: {iteration_field['name']}")
    print(f"From {args.from_iteration} iteration: {source['title']} "
          f"({source['startDate']}, {source['duration']} days)")
    print(f"To {args.to_iteration} iteration: {target['title']} "
          f"({target['startDate']}, {target['duration']} days)")
    if excluded:
        print(f"Excluded statuses: {', '.join(excluded)}")
    else:
        print(f"Statuses to move: {', '.join(statuses)}")

    items = fetch_items(
        graphql, args.owner, args.number, iteration_field["id"], status_field["id"]
    )
    selection = select_items(items, source["id"], excluded, statuses)
    archived = sum(1 for item in selection.to_move if item.is_archived)
    print(f"Scanned {len(items)} project item(s); {len(selection.in_source)} in "
          f"{source['title']}; {len(selection.skipped_by_status)} skipped by status; "
          f"{len(selection.to_move)} to move" + (f" ({archived} archived)" if archived else ""))

    moved = 0
    failed = 0
    for item in selection.to_move:
        text = item.label(args.show_titles)
        if args.dry_run:
            print(f"  [DRY RUN] would move {text} [{item.status}] -> {target['title']}")
            moved += 1
            continue
        try:
            move_item(graphql, project["id"], iteration_field["id"], item, target["id"])
        except GraphQLError as e:
            print(f"  FAILED {text}: {e}", file=sys.stderr)
            failed += 1
            continue
        print(f"  moved {text} [{item.status}] -> {target['title']}")
        moved += 1

    verb = "would be moved" if args.dry_run else "moved"
    print(f"Done: {moved} item(s) {verb} to {target['title']}"
          + (f", {failed} failed" if failed else "") + ".")
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    try:
        return run(args, run_graphql)
    except ProjectIterationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
