"""Task 1.1 grading rules: criterion statuses, candidate ranking and points.

Consumes Task11Evidence only. Performs no I/O and imports no Odoo client.
"""

from application.dto.task_1_1 import (
    FILTER_MODEL,
    FILTER_NAME,
    PARTNER_FIELDS,
    PIEROGI_NAME,
    SHARE_USER_NAME,
)
from domain import CheckResult, CheckStatus, TaskResult
from domain_logic import analyze_company_domain

TASK_ID = "1.1"
CHECK_POINTS = 1  # every criterion is worth one point
MIN_UKRAINIAN_COMPANIES = 3
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
    return CheckResult(
        id=check_id,
        status=CheckStatus(status),
        max_points=CHECK_POINTS,
        expected=EXPECTED[check_id],
        actual=actual,
        evidence=tuple(evidence),
        message=message,
    )


def to_check(check_id, result, extra_evidence=()):
    status, actual, evidence, message = result
    return build_check(check_id, status, actual, list(evidence) + list(extra_evidence), message)


def connection_error_result(message, summary="Odoo connection or authentication failed."):
    """Every criterion ERROR when nothing could be assessed (no connection, login or credentials)."""
    checks = [build_check(cid, "ERROR", None, [message], summary) for cid in CHECK_IDS]
    return TaskResult(TASK_ID, checks)


def _unreadable(error):
    return "ERROR", None, [error], "Odoo data could not be read for this check."


def _review(message, evidence=()):
    return "REVIEW", None, list(evidence), message


def _missing_partner_fields(missing):
    return _review(
        "Field metadata is insufficient; run the --diagnose mode and share its output.",
        [f"Missing res.partner fields: {', '.join(missing)}."],
    )


def _absent(present, names):
    return [name for name in names if name not in present]


# Criteria 1 and 2: partner data

def check_ukrainian_companies(evidence):
    fields = evidence.partner_fields
    if fields.error is not None:
        return _unreadable(fields.error)
    missing = _absent(fields.value, ("is_company", "country_id", "active"))
    if missing:
        return _missing_partner_fields(missing)

    count = evidence.ua_active_company_count
    if count.error is not None:
        return _unreadable(count.error)
    if count.problem is not None:
        return _review(count.problem)
    evidence_lines = [f"Active companies with country code UA: {count.value}."]
    if count.value >= MIN_UKRAINIAN_COMPANIES:
        return "PASS", count.value, evidence_lines, "Enough active Ukrainian companies exist."
    return ("FAIL", count.value, evidence_lines,
            f"Fewer than {MIN_UKRAINIAN_COMPANIES} active Ukrainian companies exist.")


def check_pierogi_polska(evidence):
    fields = evidence.partner_fields
    if fields.error is not None:
        return _unreadable(fields.error)
    missing = _absent(fields.value, PARTNER_FIELDS)
    if missing:
        return _missing_partner_fields(missing)

    result = evidence.pierogi_partners
    if result.error is not None:
        return _unreadable(result.error)
    if result.problem is not None:
        return _review(result.problem)
    rows = result.value
    if not rows:
        return "FAIL", "no active record", [], f'No active res.partner named "{PIEROGI_NAME}".'
    if len(rows) > 1:
        return "REVIEW", f"{len(rows)} active records", [], \
            "Several active records share this name; it is unclear which one is meant."

    partner = rows[0]
    country_code = partner.country.code if partner.country else None
    lang = partner.lang or ""
    actual = {"is_company": partner.is_company, "country_code": country_code, "lang": lang}

    problems = []
    if partner.is_company is not True:
        problems.append("is_company is not True")
    if country_code != "PL":
        problems.append(f"country code is {country_code!r}")
    if not lang.startswith("en_"):
        problems.append(f"lang is {lang!r}")
    if problems:
        return "FAIL", actual, [], "; ".join(problems) + "."
    return "PASS", actual, [], "Pierogi Polska is an active Polish company with an English language."


# Criteria 3 to 6: ir.filters

def _is_partner_candidate(row, filter_fields):
    if "model_id" not in filter_fields:
        return True  # Cannot tell the model; criterion 1.1.3 reports REVIEW.
    return row.model_name == FILTER_MODEL


def check_record(row, evidence):
    filter_fields = evidence.filter_fields.value
    if "model_id" not in filter_fields:
        return "REVIEW", None, [], "model_id is missing from ir.filters metadata; cannot confirm the model."
    if "active" in filter_fields and row.active is not True:
        return "FAIL", "active=False", [], "The filter record is archived."
    note = "active=True" if "active" in filter_fields else "No active field on ir.filters; not required."
    return "PASS", f"model {FILTER_MODEL}", [note], f"Filter record exists for {FILTER_MODEL}."


def check_domain(row, evidence):
    if "domain" not in evidence.filter_fields.value:
        return "REVIEW", None, [], "domain is missing from ir.filters metadata."
    ua = evidence.ua_country
    if ua.error is not None:
        return "ERROR", None, [ua.error], "The UA country could not be read from res.country."
    ua_country_id = ua.value.id if ua.value is not None else None
    verdict = analyze_company_domain(row.domain_text, ua_country_id)
    lines = [f"Stored domain (truncated): {str(row.domain_text)[:300]}"]
    if ua.problem is not None:
        lines.append(ua.problem)
    return verdict.status, "domain analysed", lines, verdict.message


def check_default_scope(row, evidence):
    filter_fields = evidence.filter_fields.value
    if "is_default" not in filter_fields:
        return "REVIEW", None, [], "is_default is missing from ir.filters metadata."
    if row.is_default is not True:
        return "FAIL", "is_default=False", [], "The filter is not the default filter."
    if "action_id" not in filter_fields:
        return "REVIEW", "is_default=True", [], "action_id is missing; cannot confirm which action the filter applies to."
    contacts = evidence.contacts_action
    if contacts.error is not None:
        return "ERROR", None, [contacts.error], "The Contacts action could not be read."
    if row.embedded_action_id is not None:
        return "REVIEW", "is_default=True, embedded action bound", [], \
            "The filter is bound to an embedded action; cannot confirm it applies to the Contacts opening action."

    if row.action_id is None:
        return "PASS", "is_default=True, no action binding", [], \
            "Default filter with no action binding; it applies to all res.partner actions."
    if contacts.problem is not None:
        return "REVIEW", "is_default=True, action bound", [contacts.problem], \
            "The filter is bound to an action, but the Contacts action could not be identified."
    action = contacts.value
    if action.res_model != FILTER_MODEL:
        return "REVIEW", "is_default=True, action bound", [], \
            f"The Contacts action does not use {FILTER_MODEL}; cannot confirm the binding."
    if row.action_id == action.id:
        return "PASS", "is_default=True, bound to Contacts action", [], "Default filter for the Contacts action."
    return "FAIL", "is_default=True, bound to another action", [], \
        "The default filter is bound to a different action, not the Contacts action."


def check_access(row, evidence):
    """Sharing is decided only by user_ids; the record owner (user_id) is deliberately ignored."""
    share = evidence.share_user_id
    if share.error is not None:
        return "ERROR", None, [share.error], "The target user could not be read."
    if "user_ids" not in evidence.filter_fields.value:
        return "REVIEW", None, [], "user_ids is missing from ir.filters metadata; cannot confirm sharing."
    if share.problem is not None:
        return "REVIEW", None, [], share.problem

    shared_ids = row.user_ids
    actual = f"user_ids has {len(shared_ids)} user(s)"
    if not shared_ids:
        return ("REVIEW", actual, [],
                "user_ids is empty. Public-sharing semantics are not verified, so access cannot be confirmed.")
    if share.value in shared_ids:
        return "PASS", actual, [f"Target user id {share.value} is in user_ids."], \
            "The filter is explicitly shared with the target user."
    return "FAIL", actual, [], "The filter is shared with other users only; the target user is not in user_ids."


def evaluate_candidate(row, evidence):
    return {
        "1.1.3": check_record(row, evidence),
        "1.1.4": check_domain(row, evidence),
        "1.1.5": check_default_scope(row, evidence),
        "1.1.6": check_access(row, evidence),
    }


def candidate_score(results):
    """Rank a whole filter record by its complete evaluation: most PASS, then fewest REVIEW, then fewest ERROR."""
    statuses = [result[0] for result in results.values()]
    return statuses.count("PASS"), -statuses.count("REVIEW"), -statuses.count("ERROR")


def _all_filter_checks(status, actual, evidence_lines, message):
    return {cid: build_check(cid, status, actual, evidence_lines, message) for cid in FILTER_CHECK_IDS}


def grade_filter_checks(evidence):
    for source in (evidence.filter_fields, evidence.filters):
        if source.error is not None:
            return _all_filter_checks("ERROR", None, [source.error], "ir.filters could not be read.")
        if source.problem is not None:
            return _all_filter_checks("REVIEW", None, [source.problem], "ir.filters could not be checked.")

    rows = evidence.filters.value
    partner_rows = [row for row in rows if _is_partner_candidate(row, evidence.filter_fields.value)]
    if not rows:
        return {cid: to_check(cid, ("REVIEW", None, [], NOT_VISIBLE_MESSAGE)) for cid in FILTER_CHECK_IDS}
    if not partner_rows:
        results = {cid: ("REVIEW", None, [], "No res.partner filter to evaluate.") for cid in FILTER_CHECK_IDS}
        results["1.1.3"] = ("FAIL", f"{len(rows)} same-name record(s) for other models",
                            [], f'No "{FILTER_NAME}" filter exists for {FILTER_MODEL}.')
        return {cid: to_check(cid, results[cid]) for cid in FILTER_CHECK_IDS}

    # Each same-name record is judged on its own; criteria come from one record only.
    scored = {row.id: evaluate_candidate(row, evidence) for row in partner_rows}
    best_id = max(scored, key=lambda filter_id: candidate_score(scored[filter_id]))
    summary = [f"filter id {fid}: {candidate_score(res)[0]}/4 PASS" for fid, res in scored.items()]
    note = (f"Evaluated {len(partner_rows)} same-name {FILTER_MODEL} filter record(s); criteria 1.1.3 to 1.1.6 "
            f"all come from filter id {best_id}. " + "; ".join(summary) + ".")
    return {cid: to_check(cid, scored[best_id][cid], [note]) for cid in FILTER_CHECK_IDS}


def grade_task(evidence):
    results = {
        "1.1.1": to_check("1.1.1", check_ukrainian_companies(evidence)),
        "1.1.2": to_check("1.1.2", check_pierogi_polska(evidence)),
    }
    results.update(grade_filter_checks(evidence))
    return TaskResult(TASK_ID, [results[check_id] for check_id in CHECK_IDS])
