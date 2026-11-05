"""Student configuration: validation, selection and credential references. Temporary files only."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from infrastructure.config.students import (
    ConfigError,
    load_students,
    parse_students,
    resolve_credentials,
    select_students,
)

STUDENT = {"id": "student_01", "url": "https://one.odoo.com/", "db": "one",
           "login_env": "S1_LOGIN", "password_env": "S1_PASSWORD"}
SECOND = {"id": "student_02", "url": "https://two.odoo.com", "db": "two",
          "login_env": "S2_LOGIN", "password_env": "S2_PASSWORD",
          "share_user_id": 8, "share_user_login": "marina", "contacts_action_xmlid": "contacts.action_x"}


def config(*students):
    return {"students": [copy.deepcopy(student) for student in students]}


def with_changes(**changes):
    student = copy.deepcopy(STUDENT)
    for key, value in changes.items():
        if value is KeyError:
            del student[key]
        else:
            student[key] = value
    return config(student)


class StudentConfigTests(unittest.TestCase):
    def test_valid_file_loads_with_optional_settings_and_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "students.json"
            path.write_text(json.dumps(config(STUDENT, SECOND)), encoding="utf-8")
            first, second = load_students(path)

        self.assertEqual(first.url, "https://one.odoo.com")  # trailing slash normalised
        self.assertEqual((first.share_user_id, first.share_user_login, first.contacts_action_xmlid),
                         (None, None, None))  # unset options keep the single-database defaults
        self.assertEqual((second.share_user_id, second.share_user_login, second.contacts_action_xmlid),
                         (8, "marina", "contacts.action_x"))

    def test_invalid_configuration_is_rejected(self):
        invalid = {
            "duplicate ids": config(STUDENT, STUDENT),
            "empty id": with_changes(id=""),
            "path-like id": with_changes(id="../escape"),
            "id with separator": with_changes(id="a/b"),
            "http url": with_changes(url="http://one.odoo.com"),
            "url with credentials": with_changes(url="https://user:secret@one.odoo.com"),
            "url without host": with_changes(url="https://"),
            "missing required field": with_changes(db=KeyError),
            "empty db": with_changes(db=""),
            "unknown field": with_changes(password="plain-text"),
            "env reference that is not a name": with_changes(password_env="my password!"),
            "non-integer share_user_id": with_changes(share_user_id="7"),
            "boolean share_user_id": with_changes(share_user_id=True),
            "malformed action xml id": with_changes(contacts_action_xmlid="nodot"),
            "no students": {"students": []},
            "wrong top level": [STUDENT],
        }
        for name, data in invalid.items():
            with self.subTest(name):
                with self.assertRaises(ConfigError):
                    parse_students(data)

        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory) / "students.json"
            broken.write_text("{ not json", encoding="utf-8")
            for path in (broken, Path(directory) / "missing.json"):
                with self.subTest(str(path.name)):
                    with self.assertRaises(ConfigError):
                        load_students(path)

    def test_selection_never_falls_back_to_another_student(self):
        students = parse_students(config(STUDENT, SECOND))
        self.assertEqual([s.id for s in select_students(students, student_id="student_02")], ["student_02"])
        self.assertEqual([s.id for s in select_students(students, select_all=True)], ["student_01", "student_02"])
        for kwargs in (dict(student_id="student_99"), dict(), dict(student_id="student_01", select_all=True)):
            with self.subTest(kwargs):
                with self.assertRaises(ConfigError):
                    select_students(students, **kwargs)

    def test_credentials_come_from_the_environment_and_missing_ones_are_named_not_valued(self):
        student = parse_students(config(STUDENT))[0]
        self.assertEqual(resolve_credentials(student, {"S1_LOGIN": "a@b.test", "S1_PASSWORD": "pw"}),
                         ("a@b.test", "pw"))
        with self.assertRaises(ConfigError) as caught:
            resolve_credentials(student, {"S1_LOGIN": "a@b.test"})
        self.assertIn("S1_PASSWORD", str(caught.exception))
        self.assertNotIn("a@b.test", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
