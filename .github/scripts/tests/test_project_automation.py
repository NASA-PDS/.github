#!/usr/bin/env python3
"""Unit tests for project_automation.py.

These tests use unittest.mock to avoid any live GitHub API calls.
Run with: python3 -m pytest .github/scripts/tests/ -v
      or: python3 -m unittest .github.scripts.tests.test_project_automation -v
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Allow importing from the scripts directory without installation
sys.path.insert(0, str(Path(__file__).parent.parent))

from project_automation import (
    BUILD_LABEL_RE,
    WORK_AREA_FIELD,
    GitHubAPIError,
    GitHubProjectAutomation,
)


class TestConstants(unittest.TestCase):
    def test_build_label_re_matches_valid(self):
        for label in ("B1", "B18", "B100", "B999"):
            with self.subTest(label=label):
                self.assertIsNotNone(BUILD_LABEL_RE.match(label))

    def test_build_label_re_rejects_invalid(self):
        for label in ("bug", "B", "b18", "B18x", "sprint-backlog", ""):
            with self.subTest(label=label):
                self.assertIsNone(BUILD_LABEL_RE.match(label))

    def test_work_area_field_constant(self):
        self.assertEqual(WORK_AREA_FIELD, "Work Area")


class TestParseExistingFieldValue(unittest.TestCase):
    def setUp(self):
        self.auto = GitHubProjectAutomation()

    def test_single_select(self):
        entry = {"data_type": "single_select", "single_select_option": {"name": "Foo"}}
        self.assertEqual(self.auto._parse_existing_field_value(entry), "Foo")

    def test_single_select_missing_option(self):
        entry = {"data_type": "single_select"}
        self.assertIsNone(self.auto._parse_existing_field_value(entry))

    def test_multi_select(self):
        entry = {"data_type": "multi_select", "multi_select_options": [{"name": "A"}, {"name": "B"}]}
        self.assertEqual(self.auto._parse_existing_field_value(entry), ["A", "B"])

    def test_multi_select_empty(self):
        entry = {"data_type": "multi_select", "multi_select_options": []}
        self.assertIsNone(self.auto._parse_existing_field_value(entry))

    def test_text_value(self):
        entry = {"data_type": "text", "value": "hello"}
        self.assertEqual(self.auto._parse_existing_field_value(entry), "hello")

    def test_none_value(self):
        entry = {"data_type": "text", "value": None}
        self.assertIsNone(self.auto._parse_existing_field_value(entry))

    def test_number_value(self):
        entry = {"data_type": "number", "value": 42}
        self.assertEqual(self.auto._parse_existing_field_value(entry), 42)


class TestSetOrgIssueFieldValues(unittest.TestCase):
    def setUp(self):
        self.auto = GitHubProjectAutomation()

    def _make_existing_response(self):
        return json.dumps([
            {"issue_field_id": 1, "data_type": "single_select",
             "single_select_option": {"name": "Core Data Services"}},
            {"issue_field_id": 2, "data_type": "text", "value": "some note"},
        ])

    @patch("subprocess.run")
    def test_merges_existing_fields_before_put(self, mock_run):
        existing_raw = self._make_existing_response()
        self.auto._run_gh_api = MagicMock(return_value=existing_raw)
        mock_run.return_value = MagicMock(returncode=0)

        self.auto.set_org_issue_field_values("NASA-PDS/validate", 42, [(3, "PDS Validate")])

        put_input = mock_run.call_args.kwargs["input"]
        payload = json.loads(put_input)
        field_map = {e["field_id"]: e["value"] for e in payload["issue_field_values"]}

        # Original fields preserved
        self.assertEqual(field_map[1], "Core Data Services")
        self.assertEqual(field_map[2], "some note")
        # New field included
        self.assertEqual(field_map[3], "PDS Validate")

    def test_raises_on_get_failure(self):
        self.auto._run_gh_api = MagicMock(side_effect=GitHubAPIError("network error"))
        with self.assertRaises(GitHubAPIError) as ctx:
            self.auto.set_org_issue_field_values("NASA-PDS/validate", 42, [(1, "val")])
        self.assertIn("Failed to read existing org field values", str(ctx.exception))

    def test_raises_on_malformed_json(self):
        self.auto._run_gh_api = MagicMock(return_value="not json")
        with self.assertRaises(GitHubAPIError):
            self.auto.set_org_issue_field_values("NASA-PDS/validate", 42, [(1, "val")])

    def test_raises_on_missing_key(self):
        # entry missing 'issue_field_id'
        self.auto._run_gh_api = MagicMock(return_value=json.dumps([{"data_type": "text"}]))
        with self.assertRaises(GitHubAPIError):
            self.auto.set_org_issue_field_values("NASA-PDS/validate", 42, [(1, "val")])


class TestResolveWorkArea(unittest.TestCase):
    def setUp(self):
        self.auto = GitHubProjectAutomation()

    def test_returns_repo_work_area_when_no_parent(self):
        self.auto.get_issue_parent = MagicMock(return_value=None)
        self.auto._load_products_config = MagicMock(return_value={
            "Validate": {
                "repositories": ["validate"],
                "work_area": "Core Data Services",
                "ignore": False,
            }
        })
        result = self.auto.resolve_work_area("NASA-PDS/validate", "ISSUE_ID", "conf/fake.yaml")
        self.assertEqual(result, "Core Data Services")

    def test_walks_to_root(self):
        self.auto.get_issue_parent = MagicMock(side_effect=[
            {"id": "PARENT_ID", "repository": {"nameWithOwner": "NASA-PDS/systems-engineering"}},
            None,
        ])
        self.auto._load_products_config = MagicMock(return_value={
            "SE": {
                "repositories": ["systems-engineering"],
                "work_area": "PDS Operations",
                "ignore": False,
            }
        })
        result = self.auto.resolve_work_area("NASA-PDS/validate", "ISSUE_ID", "conf/fake.yaml")
        self.assertEqual(result, "PDS Operations")

    def test_cycle_guard_breaks_loop(self):
        # A→B→A circular parent chain should not loop forever
        self.auto.get_issue_parent = MagicMock(side_effect=[
            {"id": "B_ID", "repository": {"nameWithOwner": "NASA-PDS/other"}},
            {"id": "ISSUE_ID", "repository": {"nameWithOwner": "NASA-PDS/validate"}},
            None,  # would never be reached
        ])
        self.auto._load_products_config = MagicMock(return_value={})
        # Should not raise RecursionError or loop
        result = self.auto.resolve_work_area("NASA-PDS/validate", "ISSUE_ID", "conf/fake.yaml")
        # No match in empty config
        self.assertIsNone(result)
        # Only 2 calls (stopped at cycle), not infinite
        self.assertEqual(self.auto.get_issue_parent.call_count, 2)


class TestCascadeLabel(unittest.TestCase):
    def setUp(self):
        self.auto = GitHubProjectAutomation()

    def test_cascade_stops_on_add_failure(self):
        """Failed add on child should not recurse into grandchildren."""
        child = {"id": "CHILD_ID", "number": 2, "repository": {"nameWithOwner": "NASA-PDS/repo"}}
        grandchild = {"id": "GC_ID", "number": 3, "repository": {"nameWithOwner": "NASA-PDS/repo"}}

        call_counts = {"sub_issues": 0}

        def fake_sub_issues(issue_id):
            call_counts["sub_issues"] += 1
            if issue_id == "PARENT_ID":
                return [child]
            if issue_id == "CHILD_ID":
                return [grandchild]
            return []

        self.auto.get_issue_sub_issues = fake_sub_issues
        self.auto._run_gh_api = MagicMock(side_effect=GitHubAPIError("403 forbidden"))

        result = self.auto._cascade_label("PARENT_ID", "B18", "add")

        self.assertEqual(result, 0)
        # grandchild sub-issues should never have been fetched
        self.assertEqual(call_counts["sub_issues"], 1)

    def test_cascade_add_success(self):
        child = {"id": "CHILD_ID", "number": 2, "repository": {"nameWithOwner": "NASA-PDS/repo"}}
        self.auto.get_issue_sub_issues = MagicMock(side_effect=[[child], []])
        self.auto._run_gh_api = MagicMock(return_value="")

        result = self.auto._cascade_label("PARENT_ID", "B18", "add")
        self.assertEqual(result, 1)

    def test_cascade_remove_404_still_recurses(self):
        """404 on remove is benign — cascade should still descend."""
        child = {"id": "CHILD_ID", "number": 2, "repository": {"nameWithOwner": "NASA-PDS/repo"}}
        grandchild = {"id": "GC_ID", "number": 3, "repository": {"nameWithOwner": "NASA-PDS/repo"}}

        def fake_sub_issues(issue_id):
            if issue_id == "PARENT_ID":
                return [child]
            if issue_id == "CHILD_ID":
                return [grandchild]
            return []

        self.auto.get_issue_sub_issues = fake_sub_issues
        self.auto._run_gh_api = MagicMock(side_effect=GitHubAPIError("404 Not Found"))

        # Should not raise; grandchild should still be attempted
        result = self.auto._cascade_label("PARENT_ID", "B18", "remove")
        # Both child and grandchild attempted, both 404-skipped
        self.assertEqual(self.auto._run_gh_api.call_count, 2)


class TestFetchAllOpenIssues(unittest.TestCase):
    def setUp(self):
        self.auto = GitHubProjectAutomation()

    def test_paginates_until_short_page(self):
        page1 = [{"number": i, "node_id": f"n{i}", "title": f"Issue {i}"} for i in range(100)]
        page2 = [{"number": 100, "node_id": "n100", "title": "Issue 100"}]
        self.auto._run_gh_api = MagicMock(side_effect=[json.dumps(page1), json.dumps(page2)])
        result = self.auto._fetch_all_open_issues("NASA-PDS/validate")
        self.assertEqual(len(result), 101)
        self.assertEqual(self.auto._run_gh_api.call_count, 2)

    def test_handles_api_error_gracefully(self):
        self.auto._run_gh_api = MagicMock(side_effect=GitHubAPIError("500"))
        result = self.auto._fetch_all_open_issues("NASA-PDS/validate")
        self.assertEqual(result, [])

    def test_returns_empty_on_empty_repo(self):
        self.auto._run_gh_api = MagicMock(return_value=json.dumps([]))
        result = self.auto._fetch_all_open_issues("NASA-PDS/validate")
        self.assertEqual(result, [])

    def test_jq_filter_excludes_pull_requests(self):
        """The jq filter passed to gh must exclude PRs (select(.pull_request == null))."""
        self.auto._run_gh_api = MagicMock(return_value=json.dumps([]))
        self.auto._fetch_all_open_issues("NASA-PDS/validate")
        jq_arg = self.auto._run_gh_api.call_args[0][0][-1]
        self.assertIn("pull_request == null", jq_arg)


class TestBackfillIssue(unittest.TestCase):
    def setUp(self):
        self.auto = GitHubProjectAutomation()

    def _issue(self, number=1):
        return {"number": number, "node_id": f"n{number}", "title": f"Issue {number}"}

    def test_skips_already_set_fields(self):
        self.auto._get_current_org_field_values = MagicMock(
            return_value={WORK_AREA_FIELD: "Core Data Services", "Product": "PDS Validate"}
        )
        result = self.auto._backfill_issue(
            "NASA-PDS/validate", self._issue(),
            "Core Data Services", "PDS Validate",
            {"id": 1}, {"id": 2}, force=False, dry_run=False
        )
        self.assertEqual(result, 0)

    def test_writes_missing_fields(self):
        self.auto._get_current_org_field_values = MagicMock(
            return_value={WORK_AREA_FIELD: None, "Product": None}
        )
        self.auto.set_org_issue_field_values = MagicMock()
        result = self.auto._backfill_issue(
            "NASA-PDS/validate", self._issue(),
            "Core Data Services", "PDS Validate",
            {"id": 1}, {"id": 2}, force=False, dry_run=False
        )
        self.assertEqual(result, 1)
        self.auto.set_org_issue_field_values.assert_called_once()

    def test_dry_run_returns_1_without_writing(self):
        self.auto._get_current_org_field_values = MagicMock(
            return_value={WORK_AREA_FIELD: None, "Product": None}
        )
        self.auto.set_org_issue_field_values = MagicMock()
        result = self.auto._backfill_issue(
            "NASA-PDS/validate", self._issue(),
            "Core Data Services", "PDS Validate",
            {"id": 1}, {"id": 2}, force=False, dry_run=True
        )
        self.assertEqual(result, 1)
        self.auto.set_org_issue_field_values.assert_not_called()

    def test_force_overwrites_existing_fields(self):
        self.auto._get_current_org_field_values = MagicMock(
            return_value={WORK_AREA_FIELD: "Old Area", "Product": "Old Product"}
        )
        self.auto.set_org_issue_field_values = MagicMock()
        result = self.auto._backfill_issue(
            "NASA-PDS/validate", self._issue(),
            "Core Data Services", "PDS Validate",
            {"id": 1}, {"id": 2}, force=True, dry_run=False
        )
        self.assertEqual(result, 1)
        self.auto.set_org_issue_field_values.assert_called_once()


class TestGetIssueSubIssuesPagination(unittest.TestCase):
    def setUp(self):
        self.auto = GitHubProjectAutomation()

    def test_paginates_via_cursor(self):
        page1 = json.dumps({
            "nodes": [{"id": "A", "number": 1, "repository": {"nameWithOwner": "NASA-PDS/r", "name": "r"}}],
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
        })
        page2 = json.dumps({
            "nodes": [{"id": "B", "number": 2, "repository": {"nameWithOwner": "NASA-PDS/r", "name": "r"}}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        })
        # side_effect list: first call returns page1, second returns page2
        self.auto._run_gh_api = MagicMock(side_effect=[page1, page2])
        result = self.auto.get_issue_sub_issues("PARENT_ID")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "A")
        self.assertEqual(result[1]["id"], "B")
        self.assertEqual(self.auto._run_gh_api.call_count, 2)

    def test_returns_empty_on_null(self):
        self.auto._run_gh_api = MagicMock(return_value="null")
        result = self.auto.get_issue_sub_issues("PARENT_ID")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
