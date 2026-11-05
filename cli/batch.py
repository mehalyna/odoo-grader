"""Batch orchestration: assess each selected student with its own client and persist one report per student.

Wiring is explicit: configuration comes in as StudentConfig objects, the client factory and the store are
passed as arguments. Task rules stay in application/tasks/task_1_1.py; this module only sequences them.
"""

import secrets
from dataclasses import dataclass
from pathlib import Path

from application.tasks.task_1_1 import MANUAL_CHECKS, NOTES, connection_error_result, grade_task
from domain import TaskResult
from infrastructure.config.students import ConfigError, resolve_credentials
from infrastructure.odoo.task_1_1_reader import DEFAULT_CONTACTS_XMLID, OdooTask11Reader, ReaderOptions
from infrastructure.storage.report_store import ReportWriteError, save_report
from odoo_client import OdooAccessError
from reporting.json_report import task_result_to_dict
from reporting.student_report import student_report_to_dict


@dataclass(frozen=True)
class StudentOutcome:
    student_id: str
    result: TaskResult
    saved_path: Path | None = None
    save_error: str | None = None


def new_run_id(now):
    """Filesystem-safe and unique: UTC timestamp plus a random suffix."""
    return f"{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"


def reader_options(student):
    """Per-student lookup options; unset values keep the single-database defaults."""
    return ReaderOptions(
        share_user_id="" if student.share_user_id is None else str(student.share_user_id),
        share_user_login=student.share_user_login or "",
        contacts_action_xmlid=student.contacts_action_xmlid or DEFAULT_CONTACTS_XMLID,
    )


def assess_student(student, environ, client_factory):
    """Run task 1.1 for one student. Any failure to assess becomes an ERROR result; it never escapes."""
    try:
        login, password = resolve_credentials(student, environ)
        client = client_factory(student.url, student.db, login, password)
        return grade_task(OdooTask11Reader(client, reader_options(student)).load_evidence())
    except ConfigError as error:
        return connection_error_result(str(error), "Student credentials could not be resolved.")
    except OdooAccessError as error:
        return connection_error_result(str(error))
    except Exception as error:  # keep the batch going; report the type only, never a message that could leak
        return connection_error_result(f"unexpected {type(error).__name__}", "Assessment stopped unexpectedly.")


def run_batch(students, output_dir, *, run_id, environ, client_factory, clock, store=save_report):
    """Assess and persist each student independently. A failure for one student never stops the others."""
    outcomes = []
    for student in students:
        checked_at = clock()
        result = assess_student(student, environ, client_factory)
        report = student_report_to_dict(
            run_id=run_id,
            student_id=student.id,
            url=student.url,
            db=student.db,
            checked_at=checked_at,
            task_report=task_result_to_dict(result, MANUAL_CHECKS, NOTES),
        )
        try:
            path = store(output_dir, run_id, student.id, report)
        except ReportWriteError as error:
            outcomes.append(StudentOutcome(student.id, result, save_error=str(error)))
        else:
            outcomes.append(StudentOutcome(student.id, result, saved_path=path))
    return outcomes


def format_outcome(outcome):
    result = outcome.result
    if result.is_final:
        points = f"{result.earned_points}/{result.max_points} points"
    else:
        points = f"{result.earned_points} confirmed, {result.pending_points} pending (of {result.max_points}) points"
    saved = f"saved: {outcome.saved_path}" if outcome.saved_path else f"NOT SAVED: {outcome.save_error}"
    return f"{outcome.student_id}: {result.status.value} - {points}\n  {saved}"


def exit_code(outcomes):
    """Nonzero when any report could not be saved. Grading outcomes (including ERROR) do not affect it."""
    return 1 if any(outcome.save_error for outcome in outcomes) else 0
