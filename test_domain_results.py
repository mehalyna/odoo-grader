"""Unit tests for the domain result models. Run: .\\.venv\\Scripts\\python.exe -m unittest test_domain_results -v"""

import dataclasses
import unittest

from domain import CheckResult, CheckStatus, TaskResult

PASS, FAIL, REVIEW, ERROR = CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.REVIEW, CheckStatus.ERROR


def check(check_id, status, max_points=1):
    return CheckResult(id=check_id, status=status, max_points=max_points)


def task(*checks):
    return TaskResult(task_id="t", checks=checks)


class CheckResultTests(unittest.TestCase):
    def test_only_pass_earns_points(self):
        self.assertEqual(check("a", PASS, 2).earned_points, 2)
        for status in (FAIL, REVIEW, ERROR):
            self.assertEqual(check("a", status, 2).earned_points, 0)

    def test_review_and_error_are_pending_not_zero(self):
        for status in (REVIEW, ERROR):
            self.assertEqual(check("a", status, 2).pending_points, 2)
        for status in (PASS, FAIL):
            self.assertEqual(check("a", status, 2).pending_points, 0)

    def test_invalid_status_rejected(self):
        for bad in ("PASS", None, 1):
            with self.assertRaises(ValueError):
                CheckResult(id="a", status=bad, max_points=1)

    def test_invalid_max_points_rejected(self):
        for bad in (-1, float("nan"), float("inf"), float("-inf"), True, "1", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                check("a", PASS, bad)

    def test_zero_max_points_allowed(self):
        self.assertEqual(check("a", PASS, 0).earned_points, 0)

    def test_invalid_id_rejected(self):
        for bad in ("", None, 1):
            with self.assertRaises(ValueError):
                check(bad, PASS)

    def test_evidence_must_not_be_a_bare_string(self):
        with self.assertRaises(ValueError):
            CheckResult(id="a", status=PASS, max_points=1, evidence="text")

    def test_evidence_is_frozen_to_tuple(self):
        source = ["one"]
        result = CheckResult(id="a", status=PASS, max_points=1, evidence=source)
        source.append("two")
        self.assertEqual(result.evidence, ("one",))

    def test_check_is_immutable(self):
        result = check("a", PASS)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.status = FAIL


class TaskResultTests(unittest.TestCase):
    def test_aggregation_all_pass(self):
        result = task(check("a", PASS, 1), check("b", PASS, 2))
        self.assertEqual(result.earned_points, 3)
        self.assertEqual(result.max_points, 3)
        self.assertEqual(result.pending_points, 0)
        self.assertTrue(result.is_final)
        self.assertIs(result.status, PASS)

    def test_mixed_fail_and_review_is_fail_but_not_final(self):
        result = task(check("a", PASS, 1), check("b", FAIL, 1), check("c", REVIEW, 2))
        self.assertIs(result.status, FAIL)  # precedence: FAIL > REVIEW
        self.assertEqual(result.earned_points, 1)
        self.assertEqual(result.pending_points, 2)
        self.assertFalse(result.is_final)  # independent of precedence

    def test_error_has_highest_precedence_and_is_pending(self):
        result = task(check("a", FAIL, 1), check("b", REVIEW, 1), check("c", ERROR, 3))
        self.assertIs(result.status, ERROR)
        self.assertEqual(result.pending_points, 4)
        self.assertFalse(result.is_final)

    def test_review_only(self):
        result = task(check("a", PASS, 1), check("b", REVIEW, 1))
        self.assertIs(result.status, REVIEW)
        self.assertFalse(result.is_final)

    def test_fail_only_is_final(self):
        result = task(check("a", PASS, 1), check("b", FAIL, 1))
        self.assertIs(result.status, FAIL)
        self.assertTrue(result.is_final)
        self.assertEqual(result.pending_points, 0)

    def test_pending_points_use_each_checks_weight(self):
        result = task(check("a", REVIEW, 0.5), check("b", ERROR, 1.5), check("c", PASS, 4))
        self.assertEqual(result.pending_points, 2.0)
        self.assertEqual(result.earned_points, 4)
        self.assertEqual(result.max_points, 6.0)

    def test_empty_checks_rejected(self):
        with self.assertRaises(ValueError):
            TaskResult(task_id="t", checks=[])

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            task(check("a", PASS), check("a", FAIL))

    def test_non_check_members_rejected(self):
        with self.assertRaises(ValueError):
            TaskResult(task_id="t", checks=[check("a", PASS), "b"])

    def test_empty_task_id_rejected(self):
        with self.assertRaises(ValueError):
            TaskResult(task_id="", checks=[check("a", PASS)])

    def test_checks_collection_cannot_be_mutated_after_validation(self):
        source = [check("a", PASS)]
        result = TaskResult(task_id="t", checks=source)
        source.append(check("b", FAIL))  # later changes to the caller's list are ignored
        self.assertEqual(len(result.checks), 1)
        self.assertIsInstance(result.checks, tuple)
        with self.assertRaises(AttributeError):
            result.checks.append(check("c", PASS))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.checks = ()


if __name__ == "__main__":
    unittest.main()
