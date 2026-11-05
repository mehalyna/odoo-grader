"""Small task 1.1 fixtures: constructed evidence and a scripted Odoo client. Test-only."""

import os
from unittest import mock

from application.dto.task_1_1 import (
    FILTER_NAME,
    PARTNER_FIELDS,
    ContactsAction,
    CountryRef,
    FilterRecord,
    PartnerRecord,
    Retrieval,
    Task11Evidence,
)
from infrastructure.odoo.task_1_1_reader import FILTER_FIELDS
from odoo_client import OdooAccessError

GOOD_DOMAIN = "[('is_company', '=', True), ('active', '=', True), ('country_id.code', '=', 'UA')]"
BAD_DOMAIN = "[('country_id.code', '=', 'UA')]"  # admits individuals

PARTNER_META_NAMES = frozenset(PARTNER_FIELDS) | {"is_company", "country_id", "active"}
FILTER_META_NAMES = frozenset(FILTER_FIELDS)


def patched_env():
    """Neutral configuration; never reads .env."""
    return mock.patch.dict(os.environ, {
        "ODOO_SHARE_USER_ID": "", "ODOO_SHARE_USER_LOGIN": "",
        "ODOO_CONTACTS_ACTION_XMLID": "contacts.action_contacts",
    })


def make_partner(code="PL", lang="en_US", partner_id=1):
    return PartnerRecord(id=partner_id, is_company=True, country=CountryRef(id=5, code=code), lang=lang)


def make_filter(filter_id=1, domain=GOOD_DOMAIN, user_ids=(7,), is_default=True, action_id=None, active=True):
    return FilterRecord(id=filter_id, model_name="res.partner", domain_text=domain, user_ids=tuple(user_ids),
                        is_default=is_default, active=active, action_id=action_id, embedded_action_id=None)


def make_evidence(**overrides):
    """Evidence in which every criterion passes. Override one section to test one case."""
    values = dict(
        partner_fields=Retrieval.ok(PARTNER_META_NAMES),
        ua_active_company_count=Retrieval.ok(3),
        pierogi_partners=Retrieval.ok((make_partner(),)),
        filter_fields=Retrieval.ok(FILTER_META_NAMES),
        filters=Retrieval.ok((make_filter(),)),
        ua_country=Retrieval.ok(CountryRef(id=4242, code="UA")),
        contacts_action=Retrieval.ok(ContactsAction(id=100, res_model="res.partner")),
        share_user_id=Retrieval.ok(7),
    )
    values.update(overrides)
    return Task11Evidence(**values)


def filter_row(**overrides):
    row = {"id": 1, "name": FILTER_NAME, "model_id": "res.partner", "domain": GOOD_DOMAIN, "user_ids": [7],
           "is_default": True, "active": True, "action_id": False, "embedded_action_id": False}
    row.update(overrides)
    return row


def pierogi_row(**overrides):
    row = {"id": 9, "is_company": True, "country_id": [5, "Poland"], "lang": "en_US"}
    row.update(overrides)
    return row


class ScriptedClient:
    """Serves canned Odoo answers per model and records every call.

    fail: models (all reads) or (model, method) pairs whose calls raise OdooAccessError.
    Any model or method that is not scripted fails the test.
    """

    def __init__(self, *, partner_rows=(), filter_rows=(), ua_count=3, ua_country_rows=({"id": 4242},),
                 country_codes=None, contacts_refs=({"res_id": 100},),
                 actions=({"id": 100, "res_model": "res.partner"},), users=(7,),
                 partner_meta=PARTNER_META_NAMES, filter_meta=FILTER_META_NAMES, fail=(),
                 fail_country_by_id=False):
        self.partner_rows, self.filter_rows = list(partner_rows), list(filter_rows)
        self.ua_count, self.ua_country_rows = ua_count, list(ua_country_rows)
        self.country_codes = country_codes or {}
        self.contacts_refs, self.actions, self.users = list(contacts_refs), list(actions), list(users)
        self.partner_meta, self.filter_meta = partner_meta, filter_meta
        self.fail, self.fail_country_by_id = set(fail), fail_country_by_id
        self.calls = []

    def _enter(self, model, method):
        self.calls.append((model, method))
        if model in self.fail or (model, method) in self.fail:
            raise OdooAccessError(f"{model}.{method} failed: Fault")

    def fields_get(self, model, attributes):
        self._enter(model, "fields_get")
        names = {"res.partner": self.partner_meta, "ir.filters": self.filter_meta}[model]
        return {name: {} for name in names}

    def search_count(self, model, domain):
        self._enter(model, "search_count")
        return self.ua_count

    def search_read(self, model, domain, fields, context=None):
        self._enter(model, "search_read")
        if model == "res.partner":
            return [dict(row) for row in self.partner_rows]
        if model == "ir.filters":
            return [dict(row) for row in self.filter_rows]
        if model == "res.country":
            if domain[0][0] == "code":
                return [dict(row) for row in self.ua_country_rows]
            if self.fail_country_by_id:
                raise OdooAccessError("res.country.search_read failed: Fault")
            code = self.country_codes.get(domain[0][2])
            return [] if code is None else [{"code": code}]
        if model == "ir.model.data":
            return [dict(row) for row in self.contacts_refs]
        if model == "ir.actions.act_window":
            return [dict(row) for row in self.actions]
        if model == "res.users":
            users = [user for user in self.users if domain[0][0] != "id" or user == domain[0][2]]
            return [{"id": user} for user in users]
        raise AssertionError(f"unexpected search_read on {model}")
