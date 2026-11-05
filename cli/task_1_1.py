"""Read-only autograder for task 1.1 (Odoo 19 Contacts). CLI entry point and composition root.

Usage:
    python -m cli.task_1_1             # grade the database, JSON to stdout, summary to stderr
    python -m cli.task_1_1 --diagnose  # print metadata of the relevant fields only

Environment variables:
    ODOO_URL, ODOO_DB, ODOO_LOGIN   connection (defaults: grader.py values; login is prompted if unset)
    ODOO_PASSWORD                   optional; otherwise prompted with getpass
    ODOO_SHARE_USER_ID              user to test for "Марина"; required if several users match
    ODOO_SHARE_USER_LOGIN           alternative to ODOO_SHARE_USER_ID
    ODOO_CONTACTS_ACTION_XMLID      Contacts action (default: contacts.action_contacts)

Layers: infrastructure/odoo/task_1_1_reader.py reads evidence, application/tasks/task_1_1.py grades it.
This module wires them together and keeps the CLI output (diagnostics, manual checks, summary).
"""

import json
import socket
import sys

from application.dto.task_1_1 import FILTER_NAME, PARTNER_FIELDS  # noqa: F401  (re-exported for callers)
from application.tasks.task_1_1 import (
    TASK_ID,
    connection_error_result,
    grade_filter_checks as grade_filter_checks_from_evidence,
    grade_task,
)
from infrastructure.odoo.task_1_1_reader import FILTER_FIELDS, OdooTask11Reader
from odoo_client import OdooAccessError, OdooClient, load_credentials
from reporting.json_report import task_result_to_dict

MANUAL_CHECKS = [
    {
        "id": "1.1.5-ui",
        "status": "MANUAL",
        "message": f'Open Contacts in a fresh session and confirm that "{FILTER_NAME}" is applied automatically. '
                   "The API checks only confirm the default configuration.",
    }
]

NOTES = [
    "Only read operations are used: search_read, search_count, read and fields_get.",
    "Authorship of existing contacts is not assessed: there is no baseline snapshot.",
    "Filter sharing is decided by user_ids only; the record owner field is not used.",
]


def grade(client):
    """Compatibility wrapper: read evidence through the Odoo adapter, then grade it."""
    return grade_task(OdooTask11Reader(client).load_evidence())


def grade_filter_checks(client):
    """Compatibility wrapper: grade criteria 1.1.3 to 1.1.6 from a client."""
    return grade_filter_checks_from_evidence(OdooTask11Reader(client).load_evidence())


def diagnose(client):
    """Print metadata of relevant fields only: no record data and no full model dumps."""
    def describe(info):
        return {"type": info.get("type"), "relation": info.get("relation")}

    filter_meta = client.fields_get("ir.filters", ["type", "relation"])
    partner_meta = client.fields_get("res.partner", ["type", "relation"])
    relevant = {
        name: describe(info) for name, info in filter_meta.items()
        if name in FILTER_FIELDS or any(part in name for part in ("user", "share", "default", "action", "group"))
    }
    return {
        "task_id": TASK_ID,
        "mode": "diagnose",
        "ir.filters": dict(sorted(relevant.items())),
        "res.partner": {name: describe(partner_meta[name]) if name in partner_meta else "MISSING"
                        for name in PARTNER_FIELDS},
    }


def print_summary(result, stream):
    if result.is_final:
        points = f"{result.earned_points}/{result.max_points} points"
    else:
        points = (f"{result.earned_points} confirmed, {result.pending_points} pending "
                  f"(of {result.max_points}) points")
    print(f"Task {result.task_id}: {result.status.value} - {points}", file=stream)
    for check in result.checks:
        print(f"  [{check.status.value}] {check.id}: {check.message}", file=stream)
    for manual in MANUAL_CHECKS:
        print(f"  [{manual['status']}] {manual['id']}: {manual['message']}", file=stream)
    print("REVIEW and ERROR are not final zero scores; check the evidence in the JSON output.", file=stream)


def configure_utf8_output():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main(argv):
    configure_utf8_output()
    socket.setdefaulttimeout(60)
    try:
        url, db, login, password = load_credentials()
        client = OdooClient(url, db, login, password)
    except OdooAccessError as error:
        result = connection_error_result(str(error))
    else:
        if "--diagnose" in argv:
            print(json.dumps(diagnose(client), ensure_ascii=False, indent=2))
            return 0
        reader = OdooTask11Reader(client)
        result = grade_task(reader.load_evidence())

    report = task_result_to_dict(result, MANUAL_CHECKS, NOTES)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print_summary(result, sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
