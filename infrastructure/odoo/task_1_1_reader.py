"""Odoo adapter for task 1.1: reads evidence through the read-only OdooClient and normalises it.

The adapter decides no criterion status. It reports what it could not retrieve: a problem when
Odoo answered without usable data (absent, ambiguous, or not queried), and an error when a read
failed. Each section is read independently, so one failure keeps the other sections.
"""

import os
from dataclasses import dataclass

from application.dto.task_1_1 import (
    FILTER_NAME,
    PARTNER_FIELDS,
    PIEROGI_NAME,
    SHARE_USER_NAME,
    UA_COUNTRY_CODE,
    ContactsAction,
    CountryRef,
    FilterRecord,
    PartnerRecord,
    Retrieval,
    Task11Evidence,
)
from odoo_client import OdooAccessError

DEFAULT_CONTACTS_XMLID = "contacts.action_contacts"
FILTER_FIELDS = ("name", "model_id", "domain", "user_ids", "is_default", "active", "action_id", "embedded_action_id")
PARTNER_COUNT_FIELDS = ("is_company", "country_id", "active")


@dataclass(frozen=True)
class ReaderOptions:
    """Per-database lookup options. Defaults match the original behaviour: name match, default Contacts action."""

    share_user_id: str = ""  # takes precedence over share_user_login
    share_user_login: str = ""
    contacts_action_xmlid: str = DEFAULT_CONTACTS_XMLID

    @classmethod
    def from_environment(cls):
        """Single-database mode: ODOO_SHARE_USER_ID, ODOO_SHARE_USER_LOGIN, ODOO_CONTACTS_ACTION_XMLID."""
        return cls(
            share_user_id=os.environ.get("ODOO_SHARE_USER_ID", "").strip(),
            share_user_login=os.environ.get("ODOO_SHARE_USER_LOGIN", "").strip(),
            contacts_action_xmlid=os.environ.get("ODOO_CONTACTS_ACTION_XMLID", DEFAULT_CONTACTS_XMLID).strip(),
        )


class OdooShapeError(ValueError):
    """An Odoo value does not have the expected shape."""


class OdooTask11Reader:
    """Implements Task11DataPort structurally: load_evidence() is the only public method."""

    def __init__(self, client, options=None):
        """options=None reads the ODOO_* environment variables when evidence is loaded."""
        self._client = client
        self._options = options

    def _current_options(self):
        return self._options if self._options is not None else ReaderOptions.from_environment()

    def load_evidence(self):
        partner_fields = _guard(self._partner_field_names)
        filter_fields = _guard(self._filter_field_names)
        return Task11Evidence(
            partner_fields=partner_fields,
            ua_active_company_count=_guard(lambda: self._ua_company_count(partner_fields)),
            pierogi_partners=_guard(lambda: self._pierogi_partners(partner_fields)),
            filter_fields=filter_fields,
            filters=_guard(lambda: self._filters(filter_fields)),
            ua_country=_guard(self._ua_country),
            contacts_action=_guard(self._contacts_action),
            share_user_id=_guard(self._share_user_id),
        )

    # Field metadata

    def _partner_field_names(self):
        return Retrieval.ok(frozenset(self._client.fields_get("res.partner", ["type"])))

    def _filter_field_names(self):
        return Retrieval.ok(frozenset(self._client.fields_get("ir.filters", ["type", "relation"])))

    # Partner data (criteria 1.1.1 and 1.1.2)

    def _ua_company_count(self, partner_fields):
        if partner_fields.error is not None:
            return Retrieval.failed(partner_fields.error)
        absent = [name for name in PARTNER_COUNT_FIELDS if name not in partner_fields.value]
        if absent:
            return Retrieval.missing(f"not queried: missing res.partner fields {', '.join(absent)}")
        domain = [("is_company", "=", True), ("active", "=", True), ("country_id.code", "=", UA_COUNTRY_CODE)]
        return Retrieval.ok(self._client.search_count("res.partner", domain))

    def _pierogi_partners(self, partner_fields):
        if partner_fields.error is not None:
            return Retrieval.failed(partner_fields.error)
        absent = [name for name in PARTNER_FIELDS if name not in partner_fields.value]
        if absent:
            return Retrieval.missing(f"not queried: missing res.partner fields {', '.join(absent)}")
        rows = self._client.search_read(
            "res.partner",
            [("name", "=", PIEROGI_NAME), ("active", "=", True)],
            ["is_company", "country_id", "lang"],
        )
        return Retrieval.ok(tuple(
            PartnerRecord(
                id=row["id"],
                is_company=bool(row["is_company"]),
                country=self._country_ref(row["country_id"]),
                lang=row["lang"] or None,
            )
            for row in rows
        ))

    def _country_ref(self, value):
        """Resolve a many2one res.country value to a named CountryRef with its code, or None if unset."""
        country_id = _ref_id(value)
        if country_id is None:
            return None
        rows = self._client.search_read("res.country", [("id", "=", country_id)], ["code"])
        code = (rows[0]["code"] or None) if rows else None
        return CountryRef(id=country_id, code=code)

    def _ua_country(self):
        rows = self._client.search_read("res.country", [("code", "=", UA_COUNTRY_CODE)], ["id"])
        if len(rows) == 1:
            return Retrieval.ok(CountryRef(id=rows[0]["id"], code=UA_COUNTRY_CODE))
        return Retrieval.missing(f"Expected exactly one res.country with code UA, found {len(rows)}.")

    # ir.filters (criteria 1.1.3 to 1.1.6)

    def _filters(self, filter_fields):
        if filter_fields.error is not None:
            return Retrieval.failed(filter_fields.error)
        fields = [name for name in FILTER_FIELDS if name in filter_fields.value]
        rows = self._client.search_read(
            "ir.filters", [("name", "=", FILTER_NAME)], fields, context={"active_test": False}
        )
        return Retrieval.ok(tuple(_filter_record(row) for row in sorted(rows, key=lambda row: row["id"])))

    def _contacts_action(self):
        xmlid = self._current_options().contacts_action_xmlid
        module, _, name = xmlid.partition(".")
        refs = self._client.search_read(
            "ir.model.data",
            [("module", "=", module), ("name", "=", name), ("model", "=", "ir.actions.act_window")],
            ["res_id"],
        )
        if not refs:
            return Retrieval.missing(f"XML id {xmlid} not found")
        actions = self._client.search_read("ir.actions.act_window", [("id", "=", refs[0]["res_id"])], ["res_model"])
        if not actions:
            return Retrieval.missing(f"action for XML id {xmlid} not found")
        return Retrieval.ok(ContactsAction(id=refs[0]["res_id"], res_model=actions[0]["res_model"]))

    def _share_user_id(self):
        """Identify the user for criterion 1.1.6. Never picks one of several matches."""
        options = self._current_options()
        configured_id, configured_login = options.share_user_id, options.share_user_login
        if configured_id:
            try:
                domain = [("id", "=", int(configured_id))]
            except ValueError:
                return Retrieval.missing("ODOO_SHARE_USER_ID must be an integer")
        elif configured_login:
            domain = [("login", "=", configured_login)]
        else:
            domain = [("name", "ilike", SHARE_USER_NAME), ("active", "=", True)]

        rows = self._client.search_read("res.users", domain, ["id"])
        if len(rows) == 1:
            return Retrieval.ok(rows[0]["id"])
        if not rows:
            return Retrieval.missing(f'No user matched "{SHARE_USER_NAME}" (or the configured user).')
        return Retrieval.missing(
            f'{len(rows)} users match "{SHARE_USER_NAME}". Set ODOO_SHARE_USER_ID or '
            "ODOO_SHARE_USER_LOGIN to choose one; the first match is never selected."
        )


def _guard(read):
    """Run one section read. Access and shape failures become an explicit error for that section only."""
    try:
        return read()
    except OdooAccessError as error:
        return Retrieval.failed(str(error))
    except OdooShapeError as error:
        return Retrieval.failed(f"unexpected Odoo value: {error}")


def _filter_record(row):
    domain = row.get("domain")
    return FilterRecord(
        id=row["id"],
        model_name=_selection(row.get("model_id")),
        domain_text=domain if isinstance(domain, str) else None,
        user_ids=tuple(_int(user_id) for user_id in (row.get("user_ids") or ())),
        is_default=_flag(row.get("is_default")),
        active=_flag(row.get("active")),
        action_id=_ref_id(row.get("action_id")),
        embedded_action_id=_ref_id(row.get("embedded_action_id")),
    )


def _ref_id(value):
    """Id of a many2one value: [id, name] or False when unset. Returns None when unset."""
    if value is None or value is False:
        return None
    if isinstance(value, (list, tuple)) and value and _is_int(value[0]):
        return value[0]
    if _is_int(value):
        return value
    raise OdooShapeError(f"expected a many2one [id, name] pair or False, got {value!r}")


def _selection(value):
    if value is None or value is False or value == "":
        return None
    if isinstance(value, str):
        return value
    raise OdooShapeError(f"expected a selection string or False, got {value!r}")


def _flag(value):
    return None if value is None else bool(value)


def _int(value):
    if not _is_int(value):
        raise OdooShapeError(f"expected an integer id, got {value!r}")
    return value


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)
