"""Batch run for several students: independence, saved JSON, write failures. Fake clients, temp directories."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cli.batch import exit_code, format_outcome, run_batch
from infrastructure.config.students import parse_students
from odoo_client import OdooAccessError
from tests.modules.module_01.task_1_1.fixtures import ScriptedClient, filter_row, pierogi_row

RUN_ID = "20261105T100000Z-abcd1234"
CHECKED_AT = datetime(2026, 11, 5, 10, 0, 0, tzinfo=timezone.utc)
CHECK_IDS = ["1.1.1", "1.1.2", "1.1.3", "1.1.4", "1.1.5", "1.1.6"]
ENVIRON = {"S1_LOGIN": "one@example.test", "S1_PASSWORD": "secret-one",
           "S2_LOGIN": "two@example.test", "S2_PASSWORD": "secret-two"}


def students(**second_options):
    return parse_students({"students": [
        {"id": "student_01", "url": "https://one.odoo.com", "db": "db-one",
         "login_env": "S1_LOGIN", "password_env": "S1_PASSWORD"},
        {"id": "student_02", "url": "https://two.odoo.com", "db": "db-two",
         "login_env": "S2_LOGIN", "password_env": "S2_PASSWORD", **second_options},
    ]})


def good_client(**overrides):
    script = dict(partner_rows=[pierogi_row()], country_codes={5: "PL"}, filter_rows=[filter_row()])
    script.update(overrides)
    return ScriptedClient(**script)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def run_batch(self, selected, clients, environ=ENVIRON, **kwargs):
        calls = []

        def factory(url, db, login, password):
            calls.append((url, db, login))
            client = clients[db]
            if isinstance(client, Exception):
                raise client
            return client

        outcomes = run_batch(selected, self.out, run_id=RUN_ID, environ=environ, client_factory=factory,
                             clock=lambda: CHECKED_AT, **kwargs)
        return outcomes, calls

    def saved(self, student_id):
        return json.loads((self.out / RUN_ID / student_id / "task_1_1.json").read_text(encoding="utf-8"))

    def test_a_failed_connection_does_not_stop_the_other_student(self):
        failure = OdooAccessError("authentication failed; check database, login and password")
        outcomes, calls = self.run_batch(students(), {"db-one": good_client(), "db-two": failure})

        self.assertEqual([call[1] for call in calls], ["db-one", "db-two"])  # a separate client per student
        self.assertEqual(exit_code(outcomes), 0)
        good = self.saved("student_01")["task_report"]
        self.assertEqual((good["status"], good["earned_points"], good["max_points"]), ("PASS", 6, 6))

        failed = self.saved("student_02")["task_report"]
        self.assertEqual([check["id"] for check in failed["checks"]], CHECK_IDS)
        self.assertEqual({check["status"] for check in failed["checks"]}, {"ERROR"})
        self.assertEqual((failed["max_points"], failed["pending_points"], failed["earned_points"], failed["is_final"]),
                         (6, 6, 0, False))

    def test_saved_json_structure_and_no_secrets(self):
        self.run_batch(students()[:1], {"db-one": good_client()})
        path = self.out / RUN_ID / "student_01" / "task_1_1.json"
        text = path.read_text(encoding="utf-8")
        report = json.loads(text)

        self.assertEqual(set(report), {"schema_version", "run_id", "student_id", "database", "checked_at",
                                       "task_report"})
        self.assertEqual((report["schema_version"], report["run_id"], report["student_id"]), (1, RUN_ID, "student_01"))
        self.assertEqual(report["database"], {"url": "https://one.odoo.com", "name": "db-one"})
        self.assertEqual(report["checked_at"], "2026-11-05T10:00:00Z")
        self.assertEqual(set(report["task_report"]), {"task_id", "status", "earned_points", "max_points",
                                                      "pending_points", "is_final", "checks", "manual_checks",
                                                      "notes"})
        self.assertIn("Українські", text)  # UTF-8, not escaped
        for secret in ("one@example.test", "secret-one", "S1_LOGIN", "S1_PASSWORD"):
            self.assertNotIn(secret, text)

    def test_retrieval_failure_keeps_independent_results(self):
        client = good_client(fail={("ir.filters", "search_read")})
        self.run_batch(students()[:1], {"db-one": client})
        statuses = {check["id"]: check["status"] for check in self.saved("student_01")["task_report"]["checks"]}
        self.assertEqual(statuses, {"1.1.1": "PASS", "1.1.2": "PASS", "1.1.3": "ERROR", "1.1.4": "ERROR",
                                    "1.1.5": "ERROR", "1.1.6": "ERROR"})

    def test_credentials_are_resolved_only_for_selected_students(self):
        only_first = {"S1_LOGIN": "one@example.test", "S1_PASSWORD": "secret-one"}
        outcomes, calls = self.run_batch(students()[:1], {"db-one": good_client()}, environ=only_first)
        self.assertEqual([call[1] for call in calls], ["db-one"])
        self.assertEqual(outcomes[0].result.earned_points, 6)

        outcomes, calls = self.run_batch(students()[1:], {"db-two": good_client()}, environ=only_first)
        self.assertEqual(calls, [])  # no connection without credentials
        report = self.saved("student_02")["task_report"]
        self.assertEqual((report["pending_points"], report["is_final"]), (6, False))
        self.assertIn("S2_LOGIN", json.dumps(report))  # the variable name is reported, never a value

    def test_per_student_options_reach_the_grader(self):
        # Two users match "Марина": without an option the check is REVIEW; share_user_id picks one.
        clients = {"db-one": good_client(users=[7, 8]), "db-two": good_client(users=[7, 8],
                   filter_rows=[filter_row(user_ids=[8])])}
        self.run_batch(students(share_user_id=8), clients)
        by_student = {sid: {c["id"]: c["status"] for c in self.saved(sid)["task_report"]["checks"]}
                      for sid in ("student_01", "student_02")}
        self.assertEqual(by_student["student_01"]["1.1.6"], "REVIEW")
        self.assertEqual(by_student["student_02"]["1.1.6"], "PASS")

    def test_write_failure_is_reported_exits_nonzero_and_other_students_continue(self):
        (self.out / RUN_ID).mkdir()
        (self.out / RUN_ID / "student_01").write_text("blocks the directory", encoding="utf-8")
        outcomes, _ = self.run_batch(students(), {"db-one": good_client(), "db-two": good_client()})

        first, second = outcomes
        self.assertIsNone(first.saved_path)
        self.assertIn("could not write", first.save_error)
        self.assertIn("NOT SAVED", format_outcome(first))
        self.assertNotIn("saved:", format_outcome(first))
        self.assertEqual(second.saved_path, self.out / RUN_ID / "student_02" / "task_1_1.json")
        self.assertTrue(second.saved_path.exists())
        self.assertEqual(exit_code(outcomes), 1)


if __name__ == "__main__":
    unittest.main()
