"""
Unit tests for move_to_next_iteration.py.

No live GitHub API calls are made: the GraphQL runner is replaced by a fake and
subprocess.run is patched where the `gh` invocation itself is tested.
Run with: python3 -m unittest discover -s .github/scripts/tests -p "test_move_to_next_iteration.py" -v
"""

import argparse
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import move_to_next_iteration as m  # noqa: E402

ITER_FIELD = "PVTIF_iter"
STATUS_FIELD = "PVTSSF_status"
PROJECT_ID = "PVT_project"


def iteration(iter_id, title, start, duration=21):
    return {"id": iter_id, "title": title, "startDate": start, "duration": duration}


# Deliberately out of order: the script must not depend on the API ordering.
CONFIG = {
    "iterations": [
        iteration("c", "19.4", "2026-11-20"),
        iteration("b", "19.3", "2026-10-30"),
        iteration("d", "19.5", "2026-12-11"),
    ],
    "completedIterations": [
        iteration("z", "18.9", "2026-08-28"),
        iteration("a", "19.2", "2026-10-09"),
        iteration("y", "19.1", "2026-09-18"),
    ],
}

FIELD_NODES = [
    {"id": "PVTF_title", "name": "Title", "dataType": "TITLE"},
    {"id": STATUS_FIELD, "name": "Status", "dataType": "SINGLE_SELECT"},
    {"id": ITER_FIELD, "name": "Sprint", "dataType": "ITERATION", "configuration": CONFIG},
]


def item_node(item_id, iteration_id=None, status=None, repo="NASA-PDS/validate", number=1,
              private=False, extra_values=0, more_values=False):
    values = []
    if iteration_id:
        values.append({"__typename": m.ITERATION_VALUE, "iterationId": iteration_id,
                       "field": {"id": ITER_FIELD}})
    if status:
        values.append({"__typename": m.SINGLE_SELECT_VALUE, "name": status,
                       "field": {"id": STATUS_FIELD}})
    # Values of other fields must be ignored, including another iteration field.
    values.append({"__typename": m.ITERATION_VALUE, "iterationId": "other",
                   "field": {"id": "PVTIF_other"}})
    values.append({"__typename": m.SINGLE_SELECT_VALUE, "name": "Done",
                   "field": {"id": "PVTSSF_other"}})
    values.extend({"__typename": "ProjectV2ItemFieldTextValue"} for _ in range(extra_values))
    return {
        "id": item_id,
        "type": "ISSUE",
        "isArchived": False,
        "content": {"__typename": "Issue", "number": number, "title": f"title {item_id}",
                    "repository": {"nameWithOwner": repo, "isPrivate": private}},
        "fieldValues": {"pageInfo": {"hasNextPage": more_values}, "nodes": values},
    }


def project_response(fields=None, has_more_fields=False):
    return {"repositoryOwner": {"projectV2": {
        "id": PROJECT_ID,
        "fields": {"pageInfo": {"hasNextPage": has_more_fields},
                   "nodes": FIELD_NODES if fields is None else fields},
    }}}


def items_response(nodes, has_next=False, cursor=None):
    return {"repositoryOwner": {"projectV2": {"items": {
        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
        "nodes": nodes,
    }}}}


class FakeGraphQL:
    """Serves project and item pages and records every call."""

    def __init__(self, pages, fail_items=()):
        self.pages = pages
        self.fail_items = set(fail_items)
        self.calls = []

    def __call__(self, query, variables):
        self.calls.append((query, dict(variables)))
        if query is m.PROJECT_QUERY:
            return project_response()
        if query is m.ITEMS_QUERY:
            index = 0 if variables.get("after") is None else int(variables["after"])
            return self.pages[index]
        if query is m.UPDATE_MUTATION:
            if variables["itemId"] in self.fail_items:
                raise m.GraphQLError("boom")
            return {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": variables["itemId"]}}}
        raise AssertionError("unexpected query")

    @property
    def mutations(self):
        return [vars_ for query, vars_ in self.calls if query is m.UPDATE_MUTATION]


def make_args(**overrides):
    values = dict(owner="NASA-PDS", number=34, iteration_field="sprint", status_field="Status",
                  from_iteration="last", to_iteration="current", excluded_statuses="Done",
                  statuses="", dry_run=False, show_titles=False)
    values.update(overrides)
    return argparse.Namespace(**values)


def run_quiet(args, graphql):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = m.run(args, graphql)
    return code, out.getvalue(), err.getvalue()


class TestPickIterations(unittest.TestCase):
    def test_last_current_next_ignore_api_order(self):
        picked = m.pick_iterations(CONFIG)
        self.assertEqual(picked["last"]["title"], "19.2")
        self.assertEqual(picked["current"]["title"], "19.3")
        self.assertEqual(picked["next"]["title"], "19.4")

    def test_missing_iterations_are_none(self):
        picked = m.pick_iterations({"iterations": [], "completedIterations": []})
        self.assertEqual(picked, {"last": None, "current": None, "next": None})

    def test_only_one_upcoming_has_no_next(self):
        picked = m.pick_iterations({"iterations": [iteration("c", "c", "2026-01-01")],
                                    "completedIterations": []})
        self.assertEqual(picked["current"]["id"], "c")
        self.assertIsNone(picked["next"])
        self.assertIsNone(picked["last"])

    def test_resolve_default_last_to_current(self):
        resolved = m.resolve_iterations(CONFIG, "last", "current")
        self.assertEqual((resolved["from"]["id"], resolved["to"]["id"]), ("a", "b"))

    def test_resolve_current_to_next(self):
        resolved = m.resolve_iterations(CONFIG, "current", "next")
        self.assertEqual((resolved["from"]["id"], resolved["to"]["id"]), ("b", "c"))

    def test_resolve_no_current_iteration_raises(self):
        config = {"iterations": [], "completedIterations": CONFIG["completedIterations"]}
        with self.assertRaisesRegex(m.ProjectConfigError, "No current iteration found"):
            m.resolve_iterations(config, "last", "current")

    def test_resolve_no_last_iteration_raises(self):
        config = {"iterations": CONFIG["iterations"], "completedIterations": []}
        with self.assertRaisesRegex(m.ProjectConfigError, "No last iteration found"):
            m.resolve_iterations(config, "last", "current")


class TestFindField(unittest.TestCase):
    def test_case_insensitive_and_trimmed(self):
        self.assertEqual(m.find_field(FIELD_NODES, " SPRINT ", "ITERATION")["id"], ITER_FIELD)

    def test_missing_field_raises(self):
        with self.assertRaisesRegex(m.ProjectConfigError, "No ITERATION field named"):
            m.find_field(FIELD_NODES, "Iteration", "ITERATION")

    def test_wrong_type_raises(self):
        with self.assertRaisesRegex(m.ProjectConfigError, "expected ITERATION"):
            m.find_field(FIELD_NODES, "Status", "ITERATION")


class TestStatusFilter(unittest.TestCase):
    def test_parse_list(self):
        self.assertEqual(m.parse_list(" Done, Deferred ,,"), ["Done", "Deferred"])
        self.assertEqual(m.parse_list(""), [])
        self.assertEqual(m.parse_list(None), [])

    def test_excluded_statuses_skip_matching(self):
        self.assertFalse(m.status_allowed("Done", ["Done"], []))
        self.assertTrue(m.status_allowed("Todo", ["Done"], []))

    def test_item_without_status_moves_when_excluding(self):
        self.assertTrue(m.status_allowed(None, ["Done"], []))

    def test_excluded_takes_precedence_over_statuses(self):
        self.assertFalse(m.status_allowed("Done", ["Done"], ["Done", "Todo"]))
        self.assertTrue(m.status_allowed("Todo", ["Done"], ["Done"]))

    def test_statuses_used_when_nothing_excluded(self):
        self.assertTrue(m.status_allowed("Todo", [], ["Todo", "Blocked"]))
        self.assertFalse(m.status_allowed("Done", [], ["Todo", "Blocked"]))
        self.assertFalse(m.status_allowed(None, [], ["Todo"]))


class TestSelectItems(unittest.TestCase):
    def setUp(self):
        nodes = [
            item_node("i1", "a", "Todo"),
            item_node("i2", "a", "Done"),
            item_node("i3", "b", "Todo"),
            item_node("i4", None, "Todo"),
            item_node("i5", "a", None),
            item_node("i6", "a", "In Progress"),
        ]
        self.items = [m.parse_item(n, ITER_FIELD, STATUS_FIELD) for n in nodes]

    def test_selects_source_iteration_not_done(self):
        selection = m.select_items(self.items, "a", ["Done"], [])
        self.assertEqual([i.id for i in selection.to_move], ["i1", "i5", "i6"])
        self.assertEqual([i.id for i in selection.in_source], ["i1", "i2", "i5", "i6"])
        self.assertEqual([i.id for i in selection.skipped_by_status], ["i2"])

    def test_statuses_only(self):
        selection = m.select_items(self.items, "a", [], ["In Progress"])
        self.assertEqual([i.id for i in selection.to_move], ["i6"])

    def test_other_fields_values_are_ignored(self):
        item = m.parse_item(item_node("x", "a", "Todo"), ITER_FIELD, STATUS_FIELD)
        self.assertEqual((item.iteration_id, item.status), ("a", "Todo"))

    def test_item_labels_hide_private_details(self):
        public = m.parse_item(item_node("p", "a", "Todo", repo="NASA-PDS/x", number=7),
                              ITER_FIELD, STATUS_FIELD)
        private = m.parse_item(item_node("q", "a", "Todo", repo="NASA-PDS/y", number=8, private=True),
                               ITER_FIELD, STATUS_FIELD)
        self.assertEqual(public.label(), "p (NASA-PDS/x#7)")
        self.assertEqual(private.label(show_titles=True), "q (private or draft item - title q)")
        self.assertNotIn("NASA-PDS/y", private.label())

    def test_too_many_field_values_raises(self):
        with self.assertRaises(m.ProjectConfigError):
            m.parse_item(item_node("x", "a", "Todo", more_values=True), ITER_FIELD, STATUS_FIELD)


class TestPagination(unittest.TestCase):
    def test_follows_cursors_until_last_page(self):
        pages = [
            items_response([item_node("i1", "a", "Todo"), item_node("i2", "a", "Todo")], True, "1"),
            items_response([item_node("i3", "a", "Todo")], True, "2"),
            items_response([item_node("i4", "a", "Todo")], False, None),
        ]
        graphql = FakeGraphQL(pages)
        items = m.fetch_items(graphql, "NASA-PDS", 34, ITER_FIELD, STATUS_FIELD)
        self.assertEqual([i.id for i in items], ["i1", "i2", "i3", "i4"])
        self.assertEqual([c[1].get("after") for c in graphql.calls], [None, "1", "2"])

    def test_single_page(self):
        graphql = FakeGraphQL([items_response([item_node("i1", "a", "Todo")])])
        items = m.fetch_items(graphql, "NASA-PDS", 34, ITER_FIELD, STATUS_FIELD)
        self.assertEqual(len(items), 1)
        self.assertEqual(len(graphql.calls), 1)

    def test_missing_project_raises(self):
        def graphql(query, variables):
            return {"repositoryOwner": {"projectV2": None}}
        with self.assertRaises(m.ProjectConfigError):
            m.fetch_items(graphql, "NASA-PDS", 99, ITER_FIELD, STATUS_FIELD)


class TestLoadProject(unittest.TestCase):
    def test_missing_project_raises(self):
        with self.assertRaisesRegex(m.ProjectConfigError, "not found"):
            m.load_project(lambda q, v: {"repositoryOwner": None}, "NASA-PDS", 1)

    def test_too_many_fields_raises(self):
        with self.assertRaisesRegex(m.ProjectConfigError, "more than 100 fields"):
            m.load_project(lambda q, v: project_response(has_more_fields=True), "NASA-PDS", 1)


class TestRun(unittest.TestCase):
    def pages(self):
        return [
            items_response([item_node("i1", "a", "Todo"), item_node("i2", "a", "Done")], True, "1"),
            items_response([item_node("i3", "a", "In Progress"), item_node("i4", "b", "Todo")]),
        ]

    def test_dry_run_sends_no_mutation(self):
        graphql = FakeGraphQL(self.pages())
        code, out, _ = run_quiet(make_args(dry_run=True), graphql)
        self.assertEqual(code, 0)
        self.assertEqual(graphql.mutations, [])
        self.assertIn("[DRY RUN] would move i1", out)
        self.assertIn("[DRY RUN] would move i3", out)
        self.assertNotIn("would move i2", out)
        self.assertIn("2 item(s) would be moved to 19.3", out)

    def test_dry_run_guard_blocks_mutations(self):
        guarded = m.read_only(FakeGraphQL([]))
        with self.assertRaisesRegex(m.ProjectIterationError, "dry-run"):
            guarded(m.UPDATE_MUTATION, {})

    def test_move_sets_target_iteration_on_each_selected_item(self):
        graphql = FakeGraphQL(self.pages())
        code, out, _ = run_quiet(make_args(), graphql)
        self.assertEqual(code, 0)
        self.assertEqual(
            graphql.mutations,
            [{"projectId": PROJECT_ID, "itemId": item_id, "fieldId": ITER_FIELD, "iterationId": "b"}
             for item_id in ("i1", "i3")],
        )
        self.assertIn("2 item(s) moved to 19.3", out)

    def test_current_to_next(self):
        graphql = FakeGraphQL(self.pages())
        run_quiet(make_args(from_iteration="current", to_iteration="next"), graphql)
        self.assertEqual([v["itemId"] for v in graphql.mutations], ["i4"])
        self.assertEqual(graphql.mutations[0]["iterationId"], "c")

    def test_failed_move_continues_and_exits_nonzero(self):
        graphql = FakeGraphQL(self.pages(), fail_items={"i1"})
        code, out, err = run_quiet(make_args(), graphql)
        self.assertEqual(code, 1)
        self.assertEqual([v["itemId"] for v in graphql.mutations], ["i1", "i3"])
        self.assertIn("FAILED i1", err)
        self.assertIn("1 item(s) moved to 19.3, 1 failed", out)

    def test_nothing_to_move_is_success(self):
        graphql = FakeGraphQL([items_response([item_node("i2", "a", "Done")])])
        code, out, _ = run_quiet(make_args(), graphql)
        self.assertEqual(code, 0)
        self.assertEqual(graphql.mutations, [])
        self.assertIn("0 item(s) moved", out)

    def test_unknown_iteration_field_raises(self):
        with self.assertRaises(m.ProjectConfigError):
            run_quiet(make_args(iteration_field="nope"), FakeGraphQL([]))


class TestRunGraphQL(unittest.TestCase):
    def completed(self, stdout="", stderr="", returncode=0):
        return MagicMock(stdout=stdout, stderr=stderr, returncode=returncode)

    def test_arguments_and_no_token_on_command_line(self):
        ok = self.completed(stdout=json.dumps({"data": {"x": 1}}))
        with patch.dict("os.environ", {"GH_TOKEN": "secret-token"}), \
                patch.object(m.subprocess, "run", return_value=ok) as run:
            data = m.run_graphql("query { x }", {"owner": "NASA-PDS", "number": 34, "after": None})
        self.assertEqual(data, {"x": 1})
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[:3], ["gh", "api", "graphql"])
        self.assertIn("number=34", cmd)
        self.assertEqual(cmd[cmd.index("number=34") - 1], "-F")
        self.assertEqual(cmd[cmd.index("owner=NASA-PDS") - 1], "-f")
        self.assertFalse(any(a.startswith("after=") for a in cmd))
        self.assertFalse(any("secret-token" in a for a in cmd))
        self.assertFalse(run.call_args[1].get("shell", False))

    def test_nonzero_exit_raises(self):
        failed = self.completed(stderr="HTTP 401", returncode=1)
        with patch.object(m.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(m.GraphQLError, "HTTP 401"):
                m.run_graphql("query { x }", {})

    def test_graphql_errors_raise(self):
        body = json.dumps({"errors": [{"message": "Could not resolve"}], "data": None})
        with patch.object(m.subprocess, "run", return_value=self.completed(stdout=body)):
            with self.assertRaisesRegex(m.GraphQLError, "Could not resolve"):
                m.run_graphql("query { x }", {})

    def test_invalid_json_raises(self):
        with patch.object(m.subprocess, "run", return_value=self.completed(stdout="not json")):
            with self.assertRaises(m.GraphQLError):
                m.run_graphql("query { x }", {})

    def test_missing_gh_raises(self):
        with patch.object(m.subprocess, "run", side_effect=FileNotFoundError("gh")):
            with self.assertRaises(m.GraphQLError):
                m.run_graphql("query { x }", {})


class TestMain(unittest.TestCase):
    def test_environment_provides_inputs(self):
        env = {"PROJECT_OWNER": "NASA-PDS", "PROJECT_NUMBER": "34", "ITERATION_FIELD": "sprint",
               "EXCLUDED_STATUSES": "Done", "DRY_RUN": "true"}
        with patch.dict("os.environ", env, clear=True):
            args = m.build_parser().parse_args([])
        self.assertEqual((args.owner, args.number, args.iteration_field), ("NASA-PDS", 34, "sprint"))
        self.assertTrue(args.dry_run)
        self.assertEqual((args.from_iteration, args.to_iteration), ("last", "current"))

    def test_empty_dry_run_env_means_real_run(self):
        with patch.dict("os.environ", {"DRY_RUN": ""}, clear=True):
            self.assertFalse(m.build_parser().parse_args([]).dry_run)

    def test_missing_status_filter_is_a_usage_error(self):
        with patch.dict("os.environ", {}, clear=True), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                m.main(["--owner", "NASA-PDS", "--number", "34", "--iteration-field", "sprint"])
        self.assertEqual(raised.exception.code, 2)

    def test_invalid_owner_is_a_usage_error(self):
        argv = ["--owner", "bad owner;", "--number", "34", "--iteration-field", "s",
                "--excluded-statuses", "Done"]
        with patch.dict("os.environ", {}, clear=True), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                m.main(argv)
        self.assertEqual(raised.exception.code, 2)

    def test_empty_token_in_actions_is_an_error(self):
        argv = ["--owner", "NASA-PDS", "--number", "34", "--iteration-field", "s",
                "--excluded-statuses", "Done"]
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true", "GH_TOKEN": ""}, clear=True), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                m.main(argv)
        self.assertEqual(raised.exception.code, 2)

    def test_api_error_exits_one(self):
        argv = ["--owner", "NASA-PDS", "--number", "34", "--iteration-field", "s",
                "--excluded-statuses", "Done", "--dry-run"]
        failing = MagicMock(stdout="", stderr="HTTP 502", returncode=1)
        with patch.dict("os.environ", {}, clear=True), \
                patch.object(m.subprocess, "run", return_value=failing), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(argv), 1)


if __name__ == "__main__":
    unittest.main()
