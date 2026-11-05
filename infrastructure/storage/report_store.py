"""Filesystem output for per-student reports: results/<run_id>/<student_id>/task_1_1.json, written atomically."""

import json
import os
import tempfile
from pathlib import Path

from infrastructure.config.students import SAFE_IDENTIFIER

REPORT_FILENAME = "task_1_1.json"


class ReportWriteError(Exception):
    """The report could not be written. Nothing is left at the target path from this attempt."""


def report_path(output_dir, run_id, student_id, filename=REPORT_FILENAME):
    for label, segment in (("run id", run_id), ("student id", student_id)):
        if not isinstance(segment, str) or not SAFE_IDENTIFIER.fullmatch(segment):
            raise ReportWriteError(f"unsafe {label} {segment!r}: refusing to build a path from it")
    return Path(output_dir) / run_id / student_id / filename


def save_report(output_dir, run_id, student_id, report, filename=REPORT_FILENAME):
    """Write the report as UTF-8 JSON via a temporary file in the same directory, then rename it into place."""
    path = report_path(output_dir, run_id, student_id, filename)
    temp_name = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".report-", suffix=".tmp")
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    except OSError as error:
        raise ReportWriteError(f"could not write {path}: {type(error).__name__}: {error.strerror or error}") from error
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
    return path
