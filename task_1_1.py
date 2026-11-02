"""Read-only autograder for task 1.1 (Odoo 19 Contacts).

Usage:
    python task_1_1.py             # grade the database, JSON to stdout, summary to stderr
    python task_1_1.py --diagnose  # print metadata of the relevant fields only

Environment variables:
    ODOO_URL, ODOO_DB, ODOO_LOGIN   connection (defaults: grader.py values; login is prompted if unset)
    ODOO_PASSWORD                   optional; otherwise prompted with getpass
    ODOO_SHARE_USER_ID              user to test for "Марина"; required if several users match
    ODOO_SHARE_USER_LOGIN           alternative to ODOO_SHARE_USER_ID
    ODOO_CONTACTS_ACTION_XMLID      Contacts action (default: contacts.action_contacts)
"""

import json
import os
import socket
import sys

from domain_logic import analyze_company_domain
from odoo_client import OdooAccessError, OdooClient, load_credentials

TASK_ID = "1.1"
MAX_POINTS = 6
MIN_UKRAINIAN_COMPANIES = 3
PIEROGI_NAME = "Pierogi Polska"
FILTER_NAME = "Українські компанії"
FILTER_MODEL = "res.partner"
SHARE_USER_NAME = "Марина"
DEFAULT_CONTACTS_XMLID = "contacts.action_contacts"

PARTNER_FIELDS = ("name", "is_company", "country_id", "lang", "active")
FILTER_FIELDS = ("name", "model_id", "domain", "user_ids", "is_default", "active", "action_id", "embedded_action_id")
CHECK_IDS = ("1.1.1", "1.1.2", "1.1.3", "1.1.4", "1.1.5", "1.1.6")
FILTER_CHECK_IDS = ("1.1.3", "1.1.4", "1.1.5", "1.1.6")

EXPECTED = {
    "1.1.1": f"At least {MIN_UKRAINIAN_COMPANIES} active res.partner records with is_company=True and country code UA",
    "1.1.2": f'Active "{PIEROGI_NAME}" with is_company=True, country code PL, lang starting with "en_"',
    "1.1.3": f'ir.filters record named "{FILTER_NAME}" for res.partner, active=True if the field exists',
    "1.1.4": "Domain logically equivalent to active companies with country code UA",
    "1.1.5": "is_default=True and the filter applies to the Contacts opening action",
    "1.1.6": f'Filter accessible to user "{SHARE_USER_NAME}" (personal share confirmed, not only public)',
}

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

NOT_VISIBLE_MESSAGE = (
    "No ir.filters record with this name is visible to the API user. A personal filter of another "
    "user can be hidden by record rules, so absence cannot be confirmed."
)


def build_check(check_id, status, actual, evidence, message):
    return {
        "id": check_id,
        "status": status,
        "expected": EXPECTED[check_id],
        "actual": actual,
        "evidence": evidence,
        "message": message,
    }


def to_check(check_id, result, extra_evidence=()):
    status, actual, evidence, message = result
    return build_check(check_id, status, actual, list(evidence) + list(extra_evidence), message)


def guarded(check_id, func):
    """Run one check; access failures become ERROR instead of stopping the grader."""
    try:
        return to_check(check_id, func())
    except OdooAccessError as error:
        return build_check(check_id, "ERROR", None, [str(error)], "Odoo data could not be read for this check.")


def missing_fields(client, model, names):
    meta = client.fields_get(model, ["type"])
    return [name for name in names if name not in meta]


# Criteria 1 and 2: partner data

def check_ukrainian_companies(client):
    missing = missing_fields(client, "res.partner", ("is_company", "country_id", "active"))
    if missing:
        return "REVIEW", None, [f"Missing res.partner fields: {', '.join(missing)}."], \
            "Field metadata is insufficient; run the --diagnose mode and share its output."

    domain = [("is_company", "=", True), ("active", "=", True), ("country_id.code", "=", "UA")]
    count = client.search_count("res.partner", domain)
    evidence = [f"Active companies with country code UA: {count}."]
    if count >= MIN_UKRAINIAN_COMPANIES:
        return "PASS", count, evidence, "Enough active Ukrainian companies exist."
    return "FAIL", count, evidence, f"Fewer than {MIN_UKRAINIAN_COMPANIES} active Ukrainian companies exist."


def check_pierogi_polska(client):
    missing = missing_fields(client, "res.partner", PARTNER_FIELDS)
    if missing:
        return "REVIEW", None, [f"Missing res.partner fields: {', '.join(missing)}."], \
            "Field metadata is insufficient; run the --diagnose mode and share its output."

    rows = client.search_read(
        "res.partner",
        [("name", "=", PIEROGI_NAME), ("active", "=", True)],
        ["is_company", "country_id", "lang"],
    )
    if not rows:
        return "FAIL", "no active record", [], f'No active res.partner named "{PIEROGI_NAME}".'
    if len(rows) > 1:
        return "REVIEW", f"{len(rows)} active records", [], \
            "Several active records share this name; it is unclear which one is meant."

    row = rows[0]
    country_code = None
    if row["country_id"]:
        countries = client.search_read("res.country", [("id", "=", row["country_id"][0])], ["code"])
        country_code = countries[0]["code"] if countries else None
    lang = row["lang"] or ""
    actual = {"is_company": row["is_company"], "country_code": country_code, "lang": lang}

    problems = []
    if row["is_company"] is not True:
        problems.append("is_company is not True")
    if country_code != "PL":
        problems.append(f"country code is {country_code!r}")
    if not lang.startswith("en_"):
        problems.append(f"lang is {lang!r}")
    if problems:
        return "FAIL", actual, [], "; ".join(problems) + "."
    return "PASS", actual, [], "Pierogi Polska is an active Polish company with an English language."


# Criteria 3 to 6: ir.filters

def load_contacts_action(client, xmlid):
    module, _, name = xmlid.partition(".")
    refs = client.search_read(
        "ir.model.data",
        [("module", "=", module), ("name", "=", name), ("model", "=", "ir.actions.act_window")],
        ["res_id"],
    )
    if not refs:
        return None, f"XML id {xmlid} not found"
    actions = client.search_read("ir.actions.act_window", [("id", "=", refs[0]["res_id"])], ["res_model"])
    if not actions:
        return None, f"action for XML id {xmlid} not found"
    return {"id": refs[0]["res_id"], "res_model": actions[0]["res_model"]}, None


def resolve_share_user(client):
    """Return (user_id, message). user_id is None unless exactly one user is identified."""
    configured_id = os.environ.get("ODOO_SHARE_USER_ID", "").strip()
    configured_login = os.environ.get("ODOO_SHARE_USER_LOGIN", "").strip()
    if configured_id:
        try:
            domain = [("id", "=", int(configured_id))]
        except ValueError:
            return None, "ODOO_SHARE_USER_ID must be an integer"
    elif configured_login:
        domain = [("login", "=", configured_login)]
    else:
        domain = [("name", "ilike", SHARE_USER_NAME), ("active", "=", True)]

    rows = client.search_read("res.users", domain, ["id"])
    if len(rows) == 1:
        return rows[0]["id"], f"Target user identified by id {rows[0]['id']}."
    if not rows:
        return None, f'No user matched "{SHARE_USER_NAME}" (or the configured user).'
    return None, (f'{len(rows)} users match "{SHARE_USER_NAME}". Set ODOO_SHARE_USER_ID or '
                  "ODOO_SHARE_USER_LOGIN to choose one; the first match is never selected.")


def load_ua_country_id(client):
    """Return (res.country id for code UA, problem). The id is resolved at run time, never hard-coded."""
    rows = client.search_read("res.country", [("code", "=", "UA")], ["id"])
    if len(rows) == 1:
        return rows[0]["id"], None
    return None, f"Expected exactly one res.country with code UA, found {len(rows)}."


def load_filter_context(client):
    meta = client.fields_get("ir.filters", ["type", "relation"])
    fields = [name for name in FILTER_FIELDS if name in meta]
    rows = client.search_read(
        "ir.filters", [("name", "=", FILTER_NAME)], fields, context={"active_test": False}
    )
    rows = sorted(rows, key=lambda row: row["id"])

    context = {
        "rows": rows,
        "fields": set(fields),
        "ua_country_id": None,
        "ua_problem": None,
        "ua_error": None,
        "contacts_action": None,
        "contacts_problem": None,
        "contacts_error": None,
        "share_user_id": None,
        "share_message": None,
        "share_error": None,
    }

    try:
        context["ua_country_id"], context["ua_problem"] = load_ua_country_id(client)
    except OdooAccessError as error:
        context["ua_error"] = str(error)

    xmlid = os.environ.get("ODOO_CONTACTS_ACTION_XMLID", DEFAULT_CONTACTS_XMLID).strip()
    try:
        context["contacts_action"], context["contacts_problem"] = load_contacts_action(client, xmlid)
    except OdooAccessError as error:
        context["contacts_error"] = str(error)

    try:
        context["share_user_id"], context["share_message"] = resolve_share_user(client)
    except OdooAccessError as error:
        context["share_error"] = str(error)
    return context


def is_partner_candidate(row, ctx):
    if "model_id" not in ctx["fields"]:
        return True  # Cannot tell the model; criterion 1.1.3 reports REVIEW.
    return row.get("model_id") == FILTER_MODEL  # model_id is a selection field


def check_record(row, ctx):
    if "model_id" not in ctx["fields"]:
        return "REVIEW", None, [], "model_id is missing from ir.filters metadata; cannot confirm the model."
    if "active" in ctx["fields"] and row.get("active") is not True:
        return "FAIL", "active=False", [], "The filter record is archived."
    note = "active=True" if "active" in ctx["fields"] else "No active field on ir.filters; not required."
    return "PASS", f"model {FILTER_MODEL}", [note], f'Filter record exists for {FILTER_MODEL}.'


def check_domain(row, ctx):
    if "domain" not in ctx["fields"]:
        return "REVIEW", None, [], "domain is missing from ir.filters metadata."
    if ctx["ua_error"]:
        return "ERROR", None, [ctx["ua_error"]], "The UA country could not be read from res.country."
    text = row.get("domain")
    verdict = analyze_company_domain(text, ctx["ua_country_id"])
    evidence = [f"Stored domain (truncated): {str(text)[:300]}"]
    if ctx["ua_problem"]:
        evidence.append(ctx["ua_problem"])
    return verdict.status, "domain analysed", evidence, verdict.message


def check_default_scope(row, ctx):
    if "is_default" not in ctx["fields"]:
        return "REVIEW", None, [], "is_default is missing from ir.filters metadata."
    if row.get("is_default") is not True:
        return "FAIL", "is_default=False", [], "The filter is not the default filter."
    if "action_id" not in ctx["fields"]:
        return "REVIEW", "is_default=True", [], "action_id is missing; cannot confirm which action the filter applies to."
    if ctx["contacts_error"]:
        return "ERROR", None, [ctx["contacts_error"]], "The Contacts action could not be read."
    if row.get("embedded_action_id"):
        return "REVIEW", "is_default=True, embedded action bound", [], \
            "The filter is bound to an embedded action; cannot confirm it applies to the Contacts opening action."

    action = row.get("action_id")
    if not action:
        return "PASS", "is_default=True, no action binding", [], \
            "Default filter with no action binding; it applies to all res.partner actions."
    if ctx["contacts_action"] is None:
        return "REVIEW", "is_default=True, action bound", [ctx["contacts_problem"]], \
            "The filter is bound to an action, but the Contacts action could not be identified."
    if ctx["contacts_action"]["res_model"] != FILTER_MODEL:
        return "REVIEW", "is_default=True, action bound", [], \
            f"The Contacts action does not use {FILTER_MODEL}; cannot confirm the binding."
    if action[0] == ctx["contacts_action"]["id"]:
        return "PASS", "is_default=True, bound to Contacts action", [], "Default filter for the Contacts action."
    return "FAIL", "is_default=True, bound to another action", [], \
        "The default filter is bound to a different action, not the Contacts action."


def check_access(row, ctx):
    """Sharing is decided only by user_ids; user_id (owner) is deliberately ignored."""
    if ctx["share_error"]:
        return "ERROR", None, [ctx["share_error"]], "The target user could not be read."
    if "user_ids" not in ctx["fields"]:
        return "REVIEW", None, [], "user_ids is missing from ir.filters metadata; cannot confirm sharing."
    if ctx["share_user_id"] is None:
        return "REVIEW", None, [], ctx["share_message"]

    shared_ids = row.get("user_ids") or []
    actual = f"user_ids has {len(shared_ids)} user(s)"
    if not shared_ids:
        return ("REVIEW", actual, [],
                "user_ids is empty. Public-sharing semantics are not verified, so access cannot be confirmed.")
    if ctx["share_user_id"] in shared_ids:
        return "PASS", actual, [f"Target user id {ctx['share_user_id']} is in user_ids."], \
            "The filter is explicitly shared with the target user."
    return "FAIL", actual, [], "The filter is shared with other users only; the target user is not in user_ids."


def evaluate_candidate(row, ctx):
    return {
        "1.1.3": check_record(row, ctx),
        "1.1.4": check_domain(row, ctx),
        "1.1.5": check_default_scope(row, ctx),
        "1.1.6": check_access(row, ctx),
    }


def candidate_score(results):
    """Rank a whole filter record by its complete evaluation: most PASS, then fewest REVIEW, then fewest ERROR."""
    statuses = [result[0] for result in results.values()]
    return statuses.count("PASS"), -statuses.count("REVIEW"), -statuses.count("ERROR")


def grade_filter_checks(client):
    try:
        ctx = load_filter_context(client)
    except OdooAccessError as error:
        return {
            cid: build_check(cid, "ERROR", None, [str(error)], "ir.filters could not be read.")
            for cid in FILTER_CHECK_IDS
        }

    rows = ctx["rows"]
    partner_rows = [row for row in rows if is_partner_candidate(row, ctx)]
    if not rows:
        results = {cid: ("REVIEW", None, [], NOT_VISIBLE_MESSAGE) for cid in FILTER_CHECK_IDS}
        return {cid: to_check(cid, results[cid]) for cid in FILTER_CHECK_IDS}
    if not partner_rows:
        results = {cid: ("REVIEW", None, [], "No res.partner filter to evaluate.") for cid in FILTER_CHECK_IDS}
        results["1.1.3"] = ("FAIL", f"{len(rows)} same-name record(s) for other models",
                            [], f'No "{FILTER_NAME}" filter exists for {FILTER_MODEL}.')
        return {cid: to_check(cid, results[cid]) for cid in FILTER_CHECK_IDS}

    # Each same-name record is judged on its own; criteria come from one record only.
    scored = {row["id"]: evaluate_candidate(row, ctx) for row in partner_rows}
    best_id = max(scored, key=lambda filter_id: candidate_score(scored[filter_id]))
    summary = [f"filter id {fid}: {candidate_score(res)[0]}/4 PASS" for fid, res in scored.items()]
    note = (f"Evaluated {len(partner_rows)} same-name {FILTER_MODEL} filter record(s); criteria 1.1.3 to 1.1.6 "
            f"all come from filter id {best_id}. " + "; ".join(summary) + ".")
    return {cid: to_check(cid, scored[best_id][cid], [note]) for cid in FILTER_CHECK_IDS}


def overall_status(checks):
    statuses = {check["status"] for check in checks}
    for status in ("ERROR", "FAIL", "REVIEW"):
        if status in statuses:
            return status
    return "PASS"


def make_report(checks):
    return {
        "task_id": TASK_ID,
        "status": overall_status(checks),
        "earned_points": sum(1 for check in checks if check["status"] == "PASS"),
        "max_points": MAX_POINTS,
        "checks": checks,
        "manual_checks": MANUAL_CHECKS,
        "notes": NOTES,
    }


def grade(client):
    results = {
        "1.1.1": guarded("1.1.1", lambda: check_ukrainian_companies(client)),
        "1.1.2": guarded("1.1.2", lambda: check_pierogi_polska(client)),
    }
    results.update(grade_filter_checks(client))
    return make_report([results[check_id] for check_id in CHECK_IDS])


def error_report(message):
    checks = [build_check(cid, "ERROR", None, [message], "Odoo connection or authentication failed.")
              for cid in CHECK_IDS]
    return make_report(checks)


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


def print_summary(report, stream):
    print(f"Task {TASK_ID}: {report['status']} - {report['earned_points']}/{MAX_POINTS} points", file=stream)
    for check in report["checks"]:
        print(f"  [{check['status']}] {check['id']}: {check['message']}", file=stream)
    for manual in report["manual_checks"]:
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
        report = error_report(str(error))
    else:
        if "--diagnose" in argv:
            print(json.dumps(diagnose(client), ensure_ascii=False, indent=2))
            return 0
        report = grade(client)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print_summary(report, sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
