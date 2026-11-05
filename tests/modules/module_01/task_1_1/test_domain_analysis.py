"""Criterion 1.1.4: logical equivalence of a stored filter domain with 'active companies in Ukraine'."""

import unittest

from domain_logic import analyze_company_domain

COMPANY = ("is_company", "=", True)
UKRAINE = ("country_id.code", "=", "UA")
UA_ID, OTHER_ID = 4242, 17  # resolved from res.country at run time in the real grader


def status(domain, ua_id=UA_ID):
    """Odoo stores ir.filters.domain as the text of a Python list literal."""
    return analyze_company_domain(repr(domain), ua_id).status


class DomainAnalysisTests(unittest.TestCase):
    def check_all(self, expected, domains):
        for domain in domains:
            with self.subTest(domain=domain):
                self.assertEqual(status(domain), expected)

    def test_company_and_ukraine_in_equivalent_forms_passes(self):
        self.check_all("PASS", [
            [COMPANY, UKRAINE],
            ["&", COMPANY, UKRAINE],
            [("country_id.code", "in", ["UA"]), ("is_company", "!=", False), ("active", "=", True)],
            ["&", COMPANY, "!", ("country_id.code", "!=", "UA")],
        ])

    def test_country_only_or_other_wrong_logic_fails(self):
        self.check_all("FAIL", [
            [UKRAINE],  # admits individuals in Ukraine
            ["|", COMPANY, UKRAINE],
            [],
            [COMPANY, ("country_id", "!=", UA_ID)],  # companies outside Ukraine
            [COMPANY, ("country_id", "in", [])],  # selects nothing
            [COMPANY, ("country_id", "not in", [])],  # selects every country
        ])
        self.assertEqual(analyze_company_domain("[]").status, "FAIL")

    def test_resolved_ukraine_membership_by_country_id(self):
        self.check_all("PASS", [
            [COMPANY, ("country_id", "in", [UA_ID])],  # no explicit active clause needed
            ["&", COMPANY, ("country_id", "=", UA_ID)],
            ["&", COMPANY, "!", ("country_id", "not in", [UA_ID])],
        ])
        self.check_all("REVIEW", [
            [COMPANY, ("country_id", "in", [UA_ID, OTHER_ID])],  # also selects another country
            [COMPANY, ("country_id", "not in", [UA_ID, OTHER_ID])],
        ])
        self.assertEqual(status([COMPANY, ("country_id", "in", [UA_ID])], ua_id=None), "REVIEW")

    def test_unsupported_or_unrecognised_expressions_need_review(self):
        for text in (
            "[('is_company', '=', True), ('country_id.code', '=', context_today())]",  # dynamic
            "__import__('os')",  # not a literal; never evaluated
            repr(["&", COMPANY]),  # malformed prefix notation
            repr([COMPANY, UKRAINE, ("city", "ilike", "Kyiv")]),  # extra unrecognised condition
        ):
            with self.subTest(text=text):
                self.assertEqual(analyze_company_domain(text, UA_ID).status, "REVIEW")


if __name__ == "__main__":
    unittest.main()
