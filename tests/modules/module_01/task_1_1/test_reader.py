"""Odoo reader for task 1.1: normalisation and honest reporting of retrieval problems. Scripted client, no network."""

import os
import unittest
from unittest import mock

from application.dto.task_1_1 import CountryRef
from application.tasks.task_1_1 import grade_task
from domain import CheckStatus
from infrastructure.odoo.task_1_1_reader import OdooTask11Reader
from odoo_client import READ_METHODS

from .fixtures import ScriptedClient, filter_row, patched_env, pierogi_row


class Task11ReaderTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patched_env())

    @staticmethod
    def load(client):
        return OdooTask11Reader(client).load_evidence()

    def test_normalises_odoo_values_and_flows_to_a_full_score(self):
        client = ScriptedClient(
            partner_rows=[pierogi_row()], country_codes={5: "PL"},
            filter_rows=[filter_row(id=5, action_id=[100, "Contacts"]), filter_row(id=2, domain=False)],
        )
        evidence = self.load(client)

        partner = evidence.pierogi_partners.value[0]
        self.assertEqual(partner.country, CountryRef(id=5, code="PL"))  # many2one pair -> named ref with code
        second, first = evidence.filters.value  # sorted by id
        self.assertEqual((second.id, second.domain_text), (2, None))  # False -> None
        self.assertEqual((first.action_id, first.embedded_action_id), (100, None))  # [id, name] -> id, False -> None
        self.assertEqual(first.user_ids, (7,))
        self.assertIs(first.is_default, True)
        self.assertEqual(first.model_name, "res.partner")

        unset = self.load(ScriptedClient(partner_rows=[pierogi_row(country_id=False, lang=False)]))
        self.assertEqual((unset.pierogi_partners.value[0].country, unset.pierogi_partners.value[0].lang),
                         (None, None))

        self.assertTrue({method for _, method in client.calls} <= READ_METHODS)
        full = self.load(ScriptedClient(partner_rows=[pierogi_row()], country_codes={5: "PL"},
                                        filter_rows=[filter_row()]))
        self.assertEqual({check.status for check in grade_task(full).checks}, {CheckStatus.PASS})

    def test_read_failures_are_errors_not_absence(self):
        cases = {
            "partner metadata": (dict(fail={("res.partner", "fields_get")}),
                                 ("partner_fields", "ua_active_company_count", "pierogi_partners"), "ua_country"),
            "filter records": (dict(fail={("ir.filters", "search_read")}), ("filters",), "ua_active_company_count"),
            "Pierogi country lookup": (dict(partner_rows=[pierogi_row()], fail_country_by_id=True),
                                       ("pierogi_partners",), "ua_country"),
            "Contacts action": (dict(fail={"ir.model.data"}), ("contacts_action",), "share_user_id"),
            "target user": (dict(fail={"res.users"}), ("share_user_id",), "contacts_action"),
        }
        for name, (script, failed_sections, independent_section) in cases.items():
            with self.subTest(name):
                evidence = self.load(ScriptedClient(**script))
                for section in failed_sections:
                    retrieval = getattr(evidence, section)
                    self.assertIsNotNone(retrieval.error, section)
                    self.assertIsNone(retrieval.problem)
                    self.assertIsNone(retrieval.value)
                self.assertIsNotNone(getattr(evidence, independent_section).value)  # unaffected section survives

    def test_absent_ambiguous_or_unqueried_data_is_a_problem_not_an_empty_value(self):
        cases = {
            "no UA country": (dict(ua_country_rows=[]), {}, "ua_country", "found 0"),
            "Contacts XML id not found": (dict(contacts_refs=[]), {}, "contacts_action", "not found"),
            "several matching users": (dict(users=[7, 8]), {}, "share_user_id", "ODOO_SHARE_USER_ID"),
            "configured user id is not an integer": (dict(), {"ODOO_SHARE_USER_ID": "abc"}, "share_user_id",
                                                     "must be an integer"),
            "required partner fields missing": (dict(partner_meta=frozenset({"name"})), {},
                                                "ua_active_company_count", "not queried"),
        }
        for name, (script, env, section, text) in cases.items():
            with self.subTest(name), mock.patch.dict(os.environ, env):
                client = ScriptedClient(**script)
                retrieval = getattr(self.load(client), section)
                self.assertIsNone(retrieval.value)
                self.assertIsNone(retrieval.error)
                self.assertIn(text, retrieval.problem)
                if name == "required partner fields missing":
                    self.assertNotIn(("res.partner", "search_count"), client.calls)

    def test_configured_user_resolves_ambiguity_but_first_match_is_never_chosen(self):
        with mock.patch.dict(os.environ, {"ODOO_SHARE_USER_ID": "8"}):
            self.assertEqual(self.load(ScriptedClient(users=[7, 8])).share_user_id.value, 8)
        self.assertIsNone(self.load(ScriptedClient(users=[7, 8])).share_user_id.value)


if __name__ == "__main__":
    unittest.main()
