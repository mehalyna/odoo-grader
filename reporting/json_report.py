"""Pure mapping from domain results to the JSON-compatible report dictionary.

No printing and no file access: callers decide what to do with the dictionary.
"""


def check_to_dict(check):
    return {
        "id": check.id,
        "status": check.status.value,
        "expected": check.expected,
        "actual": check.actual,
        "evidence": list(check.evidence),
        "message": check.message,
    }


def task_result_to_dict(task_result, manual_checks=(), notes=()):
    """Convert a TaskResult; manual checks and notes are report extras, not part of the scored result."""
    return {
        "task_id": task_result.task_id,
        "status": task_result.status.value,
        "earned_points": task_result.earned_points,
        "max_points": task_result.max_points,
        "pending_points": task_result.pending_points,
        "is_final": task_result.is_final,
        "checks": [check_to_dict(check) for check in task_result.checks],
        "manual_checks": list(manual_checks),
        "notes": list(notes),
    }
