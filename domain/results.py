"""Immutable grading result models. Standard library only: no Odoo, I/O or reporting code."""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Tuple


class CheckStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    ERROR = "ERROR"


UNRESOLVED_STATUSES = frozenset({CheckStatus.REVIEW, CheckStatus.ERROR})

# Highest precedence first.
STATUS_PRECEDENCE = (CheckStatus.ERROR, CheckStatus.FAIL, CheckStatus.REVIEW, CheckStatus.PASS)


@dataclass(frozen=True)
class CheckResult:
    id: str
    status: CheckStatus
    max_points: float
    expected: str = ""
    actual: Any = None
    evidence: Tuple[str, ...] = ()
    message: str = ""

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("check id must be a non-empty string")
        if not isinstance(self.status, CheckStatus):
            raise ValueError(f"invalid check status: {self.status!r}")
        points = self.max_points
        if isinstance(points, bool) or not isinstance(points, (int, float)):
            raise ValueError(f"max_points must be a number, got {points!r}")
        if not math.isfinite(points) or points < 0:
            raise ValueError(f"max_points must be finite and not negative, got {points!r}")
        if isinstance(self.evidence, str):
            raise ValueError("evidence must be a collection of strings, not a single string")
        object.__setattr__(self, "evidence", tuple(self.evidence))

    @property
    def is_unresolved(self):
        return self.status in UNRESOLVED_STATUSES

    @property
    def earned_points(self):
        """Confirmed points only: PASS earns max_points; every other status earns 0."""
        return self.max_points if self.status is CheckStatus.PASS else 0

    @property
    def pending_points(self):
        """Points still undecided: REVIEW and ERROR are unresolved, not a final zero."""
        return self.max_points if self.is_unresolved else 0


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    checks: Tuple[CheckResult, ...]

    def __post_init__(self):
        if not isinstance(self.task_id, str) or not self.task_id:
            raise ValueError("task_id must be a non-empty string")
        checks = tuple(self.checks)
        if not checks:
            raise ValueError("a task result needs at least one check")
        if not all(isinstance(check, CheckResult) for check in checks):
            raise ValueError("checks must contain CheckResult objects only")
        ids = [check.id for check in checks]
        duplicates = sorted({check_id for check_id in ids if ids.count(check_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate check ids: {', '.join(duplicates)}")
        object.__setattr__(self, "checks", checks)

    @property
    def earned_points(self):
        return sum(check.earned_points for check in self.checks)

    @property
    def max_points(self):
        return sum(check.max_points for check in self.checks)

    @property
    def pending_points(self):
        return sum(check.pending_points for check in self.checks)

    @property
    def is_final(self):
        """True only when no check is REVIEW or ERROR; independent of status precedence."""
        return not any(check.is_unresolved for check in self.checks)

    @property
    def status(self):
        present = {check.status for check in self.checks}
        return next(status for status in STATUS_PRECEDENCE if status in present)
