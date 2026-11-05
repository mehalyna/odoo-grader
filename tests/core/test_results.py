"""Shared result-model rules: points, status precedence, unresolved results, essential validation."""

import unittest

from domain import CheckResult, CheckStatus, TaskResult

PASS, FAIL, REVIEW, ERROR = CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.REVIEW, CheckStatus.ERROR


def check(check_id, status, max_points=1):
    return CheckResult(id=check_id, status=status, max_points=max_points)


def task(*checks):
    return TaskResult(task_id="t", checks=checks)


class CheckResultTests(unittest.TestCase):
    def test_only_pass_earns_points_and_review_error_are_pending(self):
        for status in CheckStatus:
            with self.subTest(status=status):
                result = check("a", status, 2)
                self.assertEqual(result.earned_points, 2 if status is PASS else 0)
                self.assertEqual(result.pending_points, 2 if status in (REVIEW, ERROR) else 0)

    def test_invalid_check_values_are_rejected(self):
        invalid = [
            dict(id="a", status="PASS", max_points=1),
            dict(id="a", status=PASS, max_points=-1),
            dict(id="a", status=PASS, max_points=float("nan")),
            dict(id="a", status=PASS, max_points=True),
            dict(id="", status=PASS, max_points=1),
            dict(id="a", status=PASS, max_points=1, evidence="bare string"),
        ]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    CheckResult(**kwargs)


class TaskResultTests(unittest.TestCase):
    def test_status_precedence_points_and_finality(self):
        cases = [
            # (checks, status, earned, pending, max, is_final)
            ([check("a", PASS), check("b", PASS, 2)], PASS, 3, 0, 3, True),
            ([check("a", PASS), check("b", FAIL), check("c", REVIEW, 2)], FAIL, 1, 2, 4, False),
            ([check("a", FAIL), check("b", REVIEW), check("c", ERROR, 3)], ERROR, 0, 4, 5, False),
            ([check("a", PASS), check("b", REVIEW)], REVIEW, 1, 1, 2, False),
            ([check("a", PASS), check("b", FAIL)], FAIL, 1, 0, 2, True),  # FAIL is final, REVIEW/ERROR are not
            ([check("a", REVIEW, 0.5), check("b", ERROR, 1.5), check("c", PASS, 4)], ERROR, 4, 2.0, 6.0, False),
        ]
        for checks, status, earned, pending, maximum, final in cases:
            with self.subTest(status=status, pending=pending):
                result = task(*checks)
                self.assertIs(result.status, status)
                self.assertEqual((result.earned_points, result.pending_points, result.max_points),
                                 (earned, pending, maximum))
                self.assertIs(result.is_final, final)

    def test_invalid_task_results_are_rejected(self):
        invalid = [
            dict(task_id="t", checks=[]),
            dict(task_id="", checks=[check("a", PASS)]),
            dict(task_id="t", checks=[check("a", PASS), check("a", FAIL)]),  # duplicate id
            dict(task_id="t", checks=[check("a", PASS), "b"]),  # not a CheckResult
        ]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    TaskResult(**kwargs)

    def test_collections_are_frozen_copies(self):
        checks, evidence = [check("a", PASS)], ["one"]
        result = TaskResult(task_id="t", checks=checks)
        item = CheckResult(id="a", status=PASS, max_points=1, evidence=evidence)
        checks.append(check("b", FAIL))
        evidence.append("two")
        self.assertEqual(len(result.checks), 1)
        self.assertIsInstance(result.checks, tuple)
        self.assertEqual(item.evidence, ("one",))


if __name__ == "__main__":
    unittest.main()
