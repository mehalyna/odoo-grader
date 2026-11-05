"""Task 1.1 grading rules on constructed evidence. No Odoo client is involved."""

import io
import unittest

from application.dto.task_1_1 import Retrieval
from application.tasks.task_1_1 import CHECK_IDS, grade_task
from domain import CheckStatus
from cli.task_1_1 import print_summary

from .fixtures import BAD_DOMAIN, GOOD_DOMAIN, make_evidence, make_filter, make_partner

PASS, FAIL, REVIEW, ERROR = CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.REVIEW, CheckStatus.ERROR
FILTER_IDS = ("1.1.3", "1.1.4", "1.1.5", "1.1.6")


def statuses(result):
    return {check.id: check.status for check in result.checks}


def filters(*records):
    return Retrieval.ok(tuple(records))


class Task11GradingTests(unittest.TestCase):
    def test_correct_evidence_scores_six_of_six(self):
        result = grade_task(make_evidence())
        self.assertEqual(statuses(result), {check_id: PASS for check_id in CHECK_IDS})
        self.assertEqual((result.earned_points, result.max_points, result.pending_points, result.is_final),
                         (6, 6, 0, True))

    def test_requirement_violations_fail_the_matching_criterion(self):
        cases = {
            "fewer than three Ukrainian companies": ("1.1.1", dict(ua_active_company_count=Retrieval.ok(2))),
            "Pierogi Polska in another country": ("1.1.2", dict(pierogi_partners=Retrieval.ok((make_partner("DE"),)))),
            "Pierogi Polska with a non-English language": (
                "1.1.2", dict(pierogi_partners=Retrieval.ok((make_partner(lang="pl_PL"),)))),
            "no active Pierogi Polska": ("1.1.2", dict(pierogi_partners=Retrieval.ok(()))),
            "archived filter": ("1.1.3", dict(filters=filters(make_filter(active=False)))),
            "domain admits individuals": ("1.1.4", dict(filters=filters(make_filter(domain=BAD_DOMAIN)))),
            "filter is not default": ("1.1.5", dict(filters=filters(make_filter(is_default=False)))),
            "default for another action": ("1.1.5", dict(filters=filters(make_filter(action_id=999)))),
            "not shared with the target user": ("1.1.6", dict(filters=filters(make_filter(user_ids=(9,))))),
        }
        for name, (check_id, overrides) in cases.items():
            with self.subTest(name):
                result = grade_task(make_evidence(**overrides))
                self.assertEqual(statuses(result)[check_id], FAIL)
                self.assertTrue(result.is_final)

    def test_ambiguous_evidence_is_review_not_fail(self):
        cases = {
            "two active Pierogi Polska records": (
                ("1.1.2",), dict(pierogi_partners=Retrieval.ok((make_partner(), make_partner(partner_id=2))))),
            "no filter record visible": (FILTER_IDS, dict(filters=filters())),
            "target user ambiguous": (("1.1.6",), dict(share_user_id=Retrieval.missing("2 users match"))),
            "filter shared with nobody": (("1.1.6",), dict(filters=filters(make_filter(user_ids=())))),
            "Contacts action not found": (
                ("1.1.5",), dict(filters=filters(make_filter(action_id=100)),
                                 contacts_action=Retrieval.missing("XML id contacts.x not found"))),
        }
        for name, (check_ids, overrides) in cases.items():
            with self.subTest(name):
                result = grade_task(make_evidence(**overrides))
                for check_id in check_ids:
                    self.assertEqual(statuses(result)[check_id], REVIEW, check_id)
                self.assertFalse(result.is_final)

    def test_retrieval_failure_is_error_and_keeps_independent_results(self):
        failed = Retrieval.failed("Odoo read failed")
        bound = filters(make_filter(action_id=100))  # makes the Contacts action matter for 1.1.5
        cases = {
            "partner metadata": (dict(partner_fields=failed), ("1.1.1", "1.1.2")),
            "company count": (dict(ua_active_company_count=failed), ("1.1.1",)),
            "Pierogi lookup": (dict(pierogi_partners=failed), ("1.1.2",)),
            "filter metadata": (dict(filter_fields=failed), FILTER_IDS),
            "filter records": (dict(filters=failed), FILTER_IDS),
            "UA country": (dict(ua_country=failed), ("1.1.4",)),
            "Contacts action": (dict(filters=bound, contacts_action=failed), ("1.1.5",)),
            "target user": (dict(share_user_id=failed), ("1.1.6",)),
        }
        for name, (overrides, error_ids) in cases.items():
            with self.subTest(name):
                result = grade_task(make_evidence(**overrides))
                expected = {check_id: ERROR if check_id in error_ids else PASS for check_id in CHECK_IDS}
                self.assertEqual(statuses(result), expected)  # ERROR, never FAIL; the rest keep their result
                self.assertEqual(result.pending_points, len(error_ids))
                self.assertFalse(result.is_final)

    def test_filter_candidates_are_never_combined(self):
        # A: correct domain, shared with nobody (1.1.6 REVIEW). B: wrong domain, shared with the user.
        # B is the better complete record, so all of 1.1.3-1.1.6 come from B: 3 points, not the 4 a mix would give.
        a = make_filter(1, domain=GOOD_DOMAIN, user_ids=())
        b = make_filter(2, domain=BAD_DOMAIN, user_ids=(7,))
        for order in ((a, b), (b, a)):
            with self.subTest(order=[record.id for record in order]):
                result = grade_task(make_evidence(filters=filters(*order)))
                self.assertEqual(statuses(result)["1.1.4"], FAIL)
                self.assertEqual(statuses(result)["1.1.6"], PASS)
                self.assertEqual(sum(statuses(result)[cid] is PASS for cid in FILTER_IDS), 3)
                by_id = {check.id: check for check in result.checks}
                for check_id in FILTER_IDS:
                    self.assertTrue(any("filter id 2" in line for line in by_id[check_id].evidence), check_id)

    def test_summary_shows_pending_points_only_when_unresolved(self):
        final, pending = io.StringIO(), io.StringIO()
        print_summary(grade_task(make_evidence()), final)
        print_summary(grade_task(make_evidence(filters=filters(make_filter(user_ids=())))), pending)
        self.assertIn("Task 1.1: PASS - 6/6 points", final.getvalue())
        self.assertNotIn("pending", final.getvalue().splitlines()[0])
        self.assertIn("Task 1.1: REVIEW - 5 confirmed, 1 pending (of 6) points", pending.getvalue())


if __name__ == "__main__":
    unittest.main()
