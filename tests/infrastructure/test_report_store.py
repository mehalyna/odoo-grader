"""Atomic UTF-8 report output and path safety. Temporary directories only."""

import json
import tempfile
import unittest
from pathlib import Path

from infrastructure.storage.report_store import ReportWriteError, save_report


class ReportStoreTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_report_is_written_as_utf8_json_without_leftovers(self):
        path = save_report(self.root, "run-1", "student_01", {"text": "Українські компанії"})
        self.assertEqual(path, self.root / "run-1" / "student_01" / "task_1_1.json")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"text": "Українські компанії"})
        self.assertIn("Українські", path.read_text(encoding="utf-8"))  # not \u-escaped
        self.assertEqual([item.name for item in path.parent.iterdir()], ["task_1_1.json"])  # no temp file left

    def test_unsafe_ids_and_blocked_directories_fail_clearly_without_writing(self):
        for run_id, student_id in (("run-1", "../escape"), ("run-1", "a/b"), ("..", "student_01"), ("run-1", "")):
            with self.subTest(run_id=run_id, student_id=student_id):
                with self.assertRaises(ReportWriteError):
                    save_report(self.root, run_id, student_id, {})
        self.assertEqual(list(self.root.iterdir()), [])

        (self.root / "run-2").write_text("a file where the run directory should be", encoding="utf-8")
        with self.assertRaises(ReportWriteError):
            save_report(self.root, "run-2", "student_01", {})


if __name__ == "__main__":
    unittest.main()
