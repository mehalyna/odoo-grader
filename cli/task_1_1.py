"""Read-only autograder for task 1.1 (Odoo 19 Contacts). CLI entry point and composition root.

Usage (run from the repository root):
    python -m cli.task_1_1                       # one database from .env: JSON to stdout, summary to stderr
    python -m cli.task_1_1 --diagnose            # print metadata of the relevant fields only
    python -m cli.task_1_1 --config students.json --student student_01
    python -m cli.task_1_1 --config students.json --all [--output-dir results]

Single-database environment variables:
    ODOO_URL, ODOO_DB, ODOO_LOGIN   connection (defaults: grader.py values; login is prompted if unset)
    ODOO_PASSWORD                   optional; otherwise prompted with getpass
    ODOO_SHARE_USER_ID              user to test for "Марина"; required if several users match
    ODOO_SHARE_USER_LOGIN           alternative to ODOO_SHARE_USER_ID
    ODOO_CONTACTS_ACTION_XMLID      Contacts action (default: contacts.action_contacts)

With --config, each student's URL, database and credential variable names come from the JSON file and the
sharing user and Contacts action from optional per-student fields; the ODOO_* variables above are not used.

Layers: infrastructure/odoo/task_1_1_reader.py reads evidence, application/tasks/task_1_1.py grades it,
cli/batch.py runs it per student. This module wires them together and keeps the CLI output.
"""

import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

from application.dto.task_1_1 import PARTNER_FIELDS
from application.tasks.task_1_1 import (
    MANUAL_CHECKS,
    NOTES,
    TASK_ID,
    connection_error_result,
    grade_filter_checks as grade_filter_checks_from_evidence,
    grade_task,
)
from cli.batch import exit_code, format_outcome, new_run_id, run_batch
from infrastructure.config.students import ConfigError, load_students, select_students
from infrastructure.odoo.task_1_1_reader import FILTER_FIELDS, OdooTask11Reader
from odoo_client import OdooAccessError, OdooClient, load_credentials, load_env_file
from reporting.json_report import task_result_to_dict

DEFAULT_OUTPUT_DIR = "results"


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


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m cli.task_1_1", description="Grade Odoo task 1.1 (read-only).")
    parser.add_argument("--diagnose", action="store_true", help="print field metadata only (single database)")
    parser.add_argument("--config", metavar="FILE", help="students JSON file (see students.example.json)")
    parser.add_argument("--student", metavar="ID", help="grade one configured student (requires --config)")
    parser.add_argument("--all", action="store_true", dest="all_students",
                        help="grade every configured student (requires --config)")
    parser.add_argument("--output-dir", metavar="DIR",
                        help=f"where reports are written (requires --config; default: {DEFAULT_OUTPUT_DIR})")
    args = parser.parse_args(argv)

    if args.config is None:
        if args.student is not None or args.all_students or args.output_dir is not None:
            parser.error("--student, --all and --output-dir require --config")
    else:
        if args.diagnose:
            parser.error("--diagnose cannot be combined with --config")
        if (args.student is None) == (not args.all_students):
            parser.error("--config requires exactly one of --student or --all")
    return args


def run_configured(args):
    """Multi-student mode. Configuration is validated before any connection or credential lookup."""
    try:
        selected = select_students(load_students(args.config), args.student, args.all_students)
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    load_env_file()
    run_id = new_run_id(datetime.now(timezone.utc))
    outcomes = run_batch(
        selected,
        Path(args.output_dir or DEFAULT_OUTPUT_DIR),
        run_id=run_id,
        environ=os.environ,
        client_factory=OdooClient,
        clock=lambda: datetime.now(timezone.utc),
    )
    print(f"Run {run_id}")
    for outcome in outcomes:
        print(format_outcome(outcome))
        if outcome.save_error:
            print(f"ERROR: report for {outcome.student_id} was not saved: {outcome.save_error}", file=sys.stderr)
    return exit_code(outcomes)


def main(argv):
    args = parse_args(argv)
    configure_utf8_output()
    socket.setdefaulttimeout(60)
    if args.config is not None:
        return run_configured(args)

    try:
        url, db, login, password = load_credentials()
        client = OdooClient(url, db, login, password)
    except OdooAccessError as error:
        result = connection_error_result(str(error))
    else:
        if args.diagnose:
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
