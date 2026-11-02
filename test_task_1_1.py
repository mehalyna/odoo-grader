"""Offline tests for task 1.1 filter logic using a fake client. Run: python -m unittest test_task_1_1 -v"""

import os
import unittest
from unittest import mock

from reporting.json_report import check_to_dict
from task_1_1 import FILTER_NAME, PARTNER_FIELDS, grade_filter_checks, resolve_share_user

GOOD_DOMAIN = "[('is_company', '=', True), ('active', '=', True), ('country_id.code', '=', 'UA')]"
BAD_DOMAIN = "[('country_id.code', '=', 'UA')]"  # admits individuals

FILTER_META = {
    "name": {"type": "char"},
    "model_id": {"type": "selection"},
    "domain": {"type": "text"},
    "user_ids": {"type": "many2many", "relation": "res.users"},
    "is_default": {"type": "boolean"},
    "active": {"type": "boolean"},
    "action_id": {"type": "many2one", "relation": "ir.actions.actions"},
    "embedded_action_id": {"type": "many2one", "relation": "ir.embedded.actions"},
}


def make_filter(filter_id, domain=GOOD_DOMAIN, user_ids=(), is_default=True, action_id=False):
    return {
        "id": filter_id,
        "name": FILTER_NAME,
        "model_id": "res.partner",
        "domain": domain,
        "user_ids": list(user_ids),
        "is_default": is_default,
        "active": True,
        "action_id": [action_id, "Contacts"] if action_id else False,
        "embedded_action_id": False,
    }


class FakeClient:
    """Serves canned metadata and records; any unexpected model fails the test."""

    def __init__(self, filters, users=()):
        self.filters = filters
        self.users = list(users)

    def fields_get(self, model, attributes):
        if model == "ir.filters":
            return FILTER_META
        raise AssertionError(f"unexpected fields_get on {model}")

    def search_read(self, model, domain, fields, context=None):
        if model == "ir.filters":
            return [dict(row) for row in self.filters]
        if model == "res.users":
            users = self.users
            if domain and domain[0][0] == "id":
                users = [user for user in users if user == domain[0][2]]
            return [{"id": user} for user in users]
        if model == "res.country":
            return [{"id": 4242}]  # the UA id; must match UA_ID in test_domain_logic
        if model == "ir.model.data":
            return [{"res_id": 100}]
        if model == "ir.actions.act_window":
            return [{"id": 100, "res_model": "res.partner"}]
        raise AssertionError(f"unexpected search_read on {model}")


class FullFakeClient(FakeClient):
    """Also serves the partner data needed by criteria 1.1.1 and 1.1.2, so grade() runs end to end."""

    def fields_get(self, model, attributes):
        if model == "res.partner":
            return {name: {} for name in PARTNER_FIELDS}
        return super().fields_get(model, attributes)

    def search_count(self, model, domain):
        return 3

    def search_read(self, model, domain, fields, context=None):
        if model == "res.partner":
            return [{"id": 1, "is_company": True, "country_id": [5, "Poland"], "lang": "en_US"}]
        if model == "res.country" and domain[0][0] != "code":
            return [{"code": "PL"}]
        return super().search_read(model, domain, fields, context)


class FilterLogicTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"ODOO_SHARE_USER_ID": "", "ODOO_SHARE_USER_LOGIN": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def grade(self, filters, users=(7,)):
        return self.as_dicts(grade_filter_checks(FakeClient(filters, users)))

    @staticmethod
    def as_dicts(checks):
        return {cid: check_to_dict(check) for cid, check in checks.items()}

    def test_live_style_domain_with_country_id_passes_check_4(self):
        # Shape of the live filter: no explicit active clause, country selected by res.country id.
        domain = "[('is_company', '=', True), ('country_id', 'in', [4242])]"
        checks = self.grade([make_filter(1, domain=domain, user_ids=[7])])
        self.assertEqual(checks["1.1.4"]["status"], "PASS")

    def test_marina_included_passes(self):
        checks = self.grade([make_filter(1, user_ids=[7])])
        self.assertEqual(checks["1.1.6"]["status"], "PASS")

    def test_marina_excluded_fails(self):
        checks = self.grade([make_filter(1, user_ids=[9])])
        self.assertEqual(checks["1.1.6"]["status"], "FAIL")

    def test_empty_user_ids_gives_review(self):
        checks = self.grade([make_filter(1, user_ids=[])])
        self.assertEqual(checks["1.1.6"]["status"], "REVIEW")

    def test_owner_field_is_not_used_for_sharing(self):
        row = make_filter(1, user_ids=[])
        row["user_id"] = [7, "owner"]  # owner is Marina, but sharing must not be inferred from it
        checks = self.as_dicts(grade_filter_checks(FakeClient([row], users=[7])))
        self.assertEqual(checks["1.1.6"]["status"], "REVIEW")

    def test_ambiguous_marina_gives_review(self):
        checks = self.grade([make_filter(1, user_ids=[7])], users=[7, 8])
        self.assertEqual(checks["1.1.6"]["status"], "REVIEW")

    def test_configured_id_resolves_ambiguity(self):
        with mock.patch.dict(os.environ, {"ODOO_SHARE_USER_ID": "8"}):
            checks = self.grade([make_filter(1, user_ids=[8])], users=[7, 8])
        self.assertEqual(checks["1.1.6"]["status"], "PASS")

    def test_resolve_reports_ambiguity_without_choosing(self):
        user_id, message = resolve_share_user(FakeClient([], users=[7, 8]))
        self.assertIsNone(user_id)
        self.assertIn("ODOO_SHARE_USER_ID", message)

    def test_partial_successes_from_different_filters_are_not_combined(self):
        # Filter 1: correct domain, but not shared with Marina (criterion 6 REVIEW).
        # Filter 2: wrong domain (criterion 4 FAIL), but shared with Marina (criterion 6 PASS).
        filters = [
            make_filter(1, domain=GOOD_DOMAIN, user_ids=[]),
            make_filter(2, domain=BAD_DOMAIN, user_ids=[7]),
        ]
        checks = self.grade(filters)

        # Filter 2 has the better complete evaluation, so all of criteria 3-6 come from it alone.
        self.assertEqual(checks["1.1.4"]["status"], "FAIL")
        self.assertEqual(checks["1.1.6"]["status"], "PASS")
        for cid in ("1.1.3", "1.1.4", "1.1.5", "1.1.6"):
            self.assertTrue(any("filter id 2" in line for line in checks[cid]["evidence"]), cid)
        points = sum(1 for cid in ("1.1.3", "1.1.4", "1.1.5", "1.1.6") if checks[cid]["status"] == "PASS")
        self.assertEqual(points, 3)  # combining filter 1's domain with filter 2's sharing would give 4


if __name__ == "__main__":
    unittest.main()
