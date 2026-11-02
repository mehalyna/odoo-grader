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


if __name__ == "__main__":
    unittest.main()
