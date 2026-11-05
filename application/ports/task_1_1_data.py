"""Port: where task 1.1 evidence comes from.

Implemented by infrastructure/odoo/task_1_1_reader.py. The port exposes no Odoo client,
domain query or execute_kw; the grader depends only on the returned evidence.
"""

from typing import Protocol

from application.dto.task_1_1 import Task11Evidence


class Task11DataPort(Protocol):
    def load_evidence(self) -> Task11Evidence:
        """Return every evidence section, with per-section problems or errors. Must not raise for read failures."""
        ...
