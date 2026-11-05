"""The JSON report contract, checked once on a representative result."""

import json
import unittest

from domain import CheckResult, CheckStatus, TaskResult
from reporting.json_report import task_result_to_dict


class JsonReportContractTests(unittest.TestCase):
    def test_report_contract(self):
        result = TaskResult("t", [
            CheckResult("t.1", CheckStatus.PASS, 1, expected="e1", actual=3, evidence=["seen"], message="ok"),
            CheckResult("t.2", CheckStatus.FAIL, 1, expected="e2", actual={"k": "v"}, message="wrong"),
            CheckResult("t.3", CheckStatus.REVIEW, 2, message="unclear"),
        ])
        manual = [{"id": "t.3-ui", "status": "MANUAL", "message": "look"}]
        report = task_result_to_dict(result, manual, ["a note"])

        self.assertEqual(set(report), {"task_id", "status", "earned_points", "max_points", "pending_points",
                                       "is_final", "checks", "manual_checks", "notes"})
        self.assertEqual((report["status"], report["earned_points"], report["max_points"],
                          report["pending_points"], report["is_final"]), ("FAIL", 1, 4, 2, False))
        self.assertEqual(report["manual_checks"], manual)
        self.assertEqual(report["notes"], ["a note"])
        for check in report["checks"]:
            self.assertEqual(set(check), {"id", "status", "expected", "actual", "evidence", "message"})
            self.assertIsInstance(check["status"], str)  # Enum converted explicitly
            self.assertIsInstance(check["evidence"], list)
        self.assertEqual([check["status"] for check in report["checks"]], ["PASS", "FAIL", "REVIEW"])
        self.assertEqual(json.loads(json.dumps(report, ensure_ascii=False)), report)


if __name__ == "__main__":
    unittest.main()
