"""Regression tests for the JSON report mapping and TaskResult aggregation in task 1.1."""

import io
import json
import os
import unittest
from unittest import mock

from reporting.json_report import task_result_to_dict
from task_1_1 import MANUAL_CHECKS, NOTES, grade, print_summary
from test_task_1_1 import BAD_DOMAIN, FullFakeClient, make_filter

CHECK_KEYS = {"id", "status", "expected", "actual", "evidence", "message"}
REPORT_KEYS = {"task_id", "status", "earned_points", "max_points", "pending_points", "is_final",
               "checks", "manual_checks", "notes"}


class JsonReportTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"ODOO_SHARE_USER_ID": "", "ODOO_SHARE_USER_LOGIN": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def report(self, filters):
        result = grade(FullFakeClient(filters, users=[7]))
        return task_result_to_dict(result, MANUAL_CHECKS, NOTES)

    def test_all_pass_report(self):
        report = self.report([make_filter(1, user_ids=[7])])
        self.assertEqual(report["status"], "PASS")
        self.assertEqual((report["earned_points"], report["max_points"]), (6, 6))
        self.assertEqual(report["pending_points"], 0)
        self.assertIs(report["is_final"], True)
        self.assertEqual([check["id"] for check in report["checks"]],
                         ["1.1.1", "1.1.2", "1.1.3", "1.1.4", "1.1.5", "1.1.6"])

    def test_report_keys_and_json_compatibility(self):
        report = self.report([make_filter(1, user_ids=[7])])
        self.assertEqual(set(report), REPORT_KEYS)
        for check in report["checks"]:
            self.assertEqual(set(check), CHECK_KEYS)
            self.assertIsInstance(check["status"], str)  # Enum converted explicitly
            self.assertIsInstance(check["evidence"], list)
        self.assertEqual(report["manual_checks"], MANUAL_CHECKS)
        self.assertEqual(report["notes"], NOTES)
        json.dumps(report, ensure_ascii=False)  # must serialise without custom encoders

    def test_mixed_fail_and_review_is_fail_but_not_final(self):
        # Criterion 4 FAIL (domain admits individuals), criterion 6 REVIEW (user_ids empty).
        report = self.report([make_filter(1, domain=BAD_DOMAIN, user_ids=[])])
        statuses = {check["id"]: check["status"] for check in report["checks"]}
        self.assertEqual(statuses["1.1.4"], "FAIL")
        self.assertEqual(statuses["1.1.6"], "REVIEW")
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["earned_points"], 4)
        self.assertEqual(report["pending_points"], 1)
        self.assertIs(report["is_final"], False)

    def test_summary_shows_pending_points_only_when_not_final(self):
        final, pending = io.StringIO(), io.StringIO()
        print_summary(grade(FullFakeClient([make_filter(1, user_ids=[7])], users=[7])), final)
        print_summary(grade(FullFakeClient([make_filter(1, user_ids=[])], users=[7])), pending)
        self.assertIn("Task 1.1: PASS - 6/6 points", final.getvalue())
        self.assertNotIn("pending", final.getvalue().splitlines()[0])
        self.assertIn("Task 1.1: REVIEW - 5 confirmed, 1 pending (of 6) points", pending.getvalue())

    def test_review_only_is_pending_not_zero(self):
        report = self.report([make_filter(1, user_ids=[])])
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual((report["earned_points"], report["pending_points"]), (5, 1))
        self.assertIs(report["is_final"], False)


if __name__ == "__main__":
    unittest.main()
