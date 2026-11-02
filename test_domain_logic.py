"""Offline tests for the domain equivalence logic. Run: python -m unittest test_domain_logic -v"""

import unittest

from domain_logic import analyze_company_domain

COMPANY = ("is_company", "=", True)
UKRAINE = ("country_id.code", "=", "UA")


def as_stored(domain):
    """Odoo stores ir.filters.domain as the text of a Python list literal."""
    return repr(domain)


class DomainLogicTests(unittest.TestCase):
    def test_correct_and_passes(self):
        self.assertEqual(analyze_company_domain(as_stored([COMPANY, UKRAINE])).status, "PASS")

    def test_explicit_and_passes(self):
        self.assertEqual(analyze_company_domain(as_stored(["&", COMPANY, UKRAINE])).status, "PASS")

    def test_equivalent_forms_pass(self):
        domain = [("country_id.code", "in", ["UA"]), ("is_company", "!=", False), ("active", "=", True)]
        self.assertEqual(analyze_company_domain(as_stored(domain)).status, "PASS")

    def test_double_negation_passes(self):
        domain = ["&", COMPANY, "!", ("country_id.code", "!=", "UA")]
        self.assertEqual(analyze_company_domain(as_stored(domain)).status, "PASS")

    def test_country_only_fails(self):
        # Admits individuals located in Ukraine.
        self.assertEqual(analyze_company_domain(as_stored([UKRAINE])).status, "FAIL")

    def test_incorrect_or_fails(self):
        self.assertEqual(analyze_company_domain(as_stored(["|", COMPANY, UKRAINE])).status, "FAIL")

    def test_empty_domain_fails(self):
        self.assertEqual(analyze_company_domain("[]").status, "FAIL")

    def test_extra_restrictive_condition_gives_review(self):
        domain = [COMPANY, UKRAINE, ("city", "ilike", "Kyiv")]
        self.assertEqual(analyze_company_domain(as_stored(domain)).status, "REVIEW")

    def test_unsupported_dynamic_expression_gives_review(self):
        text = "[('is_company', '=', True), ('country_id.code', '=', context_today())]"
        self.assertEqual(analyze_company_domain(text).status, "REVIEW")

    def test_non_literal_text_gives_review(self):
        self.assertEqual(analyze_company_domain("__import__('os')").status, "REVIEW")

    def test_malformed_prefix_gives_review(self):
        self.assertEqual(analyze_company_domain(as_stored(["&", COMPANY])).status, "REVIEW")


# Resolved at run time from res.country in the real grader; any id works here.
UA_ID = 4242
OTHER_ID = 17


class CountryIdTests(unittest.TestCase):
    def verdict(self, domain, ua_id=UA_ID):
        return analyze_company_domain(as_stored(domain), ua_id).status

    def test_singleton_in_passes_without_active_clause(self):
        self.assertEqual(self.verdict([("is_company", "=", True), ("country_id", "in", [UA_ID])]), "PASS")

    def test_equals_passes(self):
        self.assertEqual(self.verdict(["&", COMPANY, ("country_id", "=", UA_ID)]), "PASS")

    def test_multiple_country_in_is_not_normalised_to_ua(self):
        # [UA, other] also selects the other country, so it must not be treated as UA-only.
        self.assertEqual(self.verdict([COMPANY, ("country_id", "in", [UA_ID, OTHER_ID])]), "REVIEW")

    def test_empty_in_selects_nothing_and_fails(self):
        self.assertEqual(self.verdict([COMPANY, ("country_id", "in", [])]), "FAIL")

    def test_not_equal_ua_selects_non_ukrainian_companies_and_fails(self):
        self.assertEqual(self.verdict([COMPANY, ("country_id", "!=", UA_ID)]), "FAIL")

    def test_double_negated_not_equal_passes(self):
        self.assertEqual(self.verdict(["&", COMPANY, "!", ("country_id", "!=", UA_ID)]), "PASS")

    def test_not_in_ua_selects_non_ukrainian_companies_and_fails(self):
        self.assertEqual(self.verdict([COMPANY, ("country_id", "not in", [UA_ID])]), "FAIL")

    def test_double_negated_not_in_ua_passes(self):
        self.assertEqual(self.verdict(["&", COMPANY, "!", ("country_id", "not in", [UA_ID])]), "PASS")

    def test_not_in_multiple_countries_is_unrecognised(self):
        self.assertEqual(self.verdict([COMPANY, ("country_id", "not in", [UA_ID, OTHER_ID])]), "REVIEW")

    def test_empty_not_in_selects_everything_and_fails(self):
        self.assertEqual(self.verdict([COMPANY, ("country_id", "not in", [])]), "FAIL")

    def test_country_id_without_resolved_ua_id_gives_review(self):
        verdict = analyze_company_domain(as_stored([COMPANY, ("country_id", "in", [UA_ID])]), None)
        self.assertEqual(verdict.status, "REVIEW")


if __name__ == "__main__":
    unittest.main()
