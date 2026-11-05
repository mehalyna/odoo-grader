"""Pure mapping of one student's task report into the persisted JSON document.

Contains no credentials or environment-variable values: only the database URL and name.
"""

from datetime import timezone

SCHEMA_VERSION = 1


def student_report_to_dict(*, run_id, student_id, url, db, checked_at, task_report):
    if checked_at.tzinfo is None:
        raise ValueError("checked_at must be timezone-aware")
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "student_id": student_id,
        "database": {"url": url, "name": db},
        "checked_at": checked_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "task_report": task_report,
    }
