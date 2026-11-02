"""Minimal read-only Odoo XML-RPC client.

Only read methods are allowed through call(), so graders built on this
client cannot create, write or delete records.
"""

import getpass
import os
import xmlrpc.client
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_URL = "https://edu-grandmas.odoo.com"
DEFAULT_DB = "edu-grandmas"
ENV_FILE = Path(__file__).resolve().parent / ".env"
READ_METHODS = frozenset({"search", "search_read", "search_count", "read", "fields_get"})


class OdooAccessError(Exception):
    """Raised when Odoo cannot be reached, rejects the login, or fails a read."""


def load_credentials():
    """Read settings from .env (if present) and environment variables; prompt only for missing credentials.

    Existing environment variables take precedence over .env values (override=False).
    """
    load_dotenv(ENV_FILE, override=False)
    url = os.environ.get("ODOO_URL") or DEFAULT_URL
    db = os.environ.get("ODOO_DB") or DEFAULT_DB
    login = os.environ.get("ODOO_LOGIN") or input("Odoo login (email): ").strip()
    password = os.environ.get("ODOO_PASSWORD") or getpass.getpass("Odoo password: ")
    return url, db, login, password


class OdooClient:
    def __init__(self, url, db, login, password):
        self.db = db
        self._password = password
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        self._object = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        try:
            self.uid = common.authenticate(db, login, password, {})
        except Exception as error:
            raise OdooAccessError(f"authentication request failed: {type(error).__name__}") from error
        if not self.uid:
            raise OdooAccessError("authentication failed; check database, login and password")

    def call(self, model, method, args, kwargs=None):
        if method not in READ_METHODS:
            raise ValueError(f"Refusing non-read Odoo method: {method}")
        try:
            return self._object.execute_kw(
                self.db, self.uid, self._password, model, method, args, kwargs or {}
            )
        except Exception as error:
            raise OdooAccessError(f"{model}.{method} failed: {type(error).__name__}") from error

    def search_read(self, model, domain, fields, context=None):
        kwargs = {"fields": fields}
        if context:
            kwargs["context"] = context
        return self.call(model, "search_read", [domain], kwargs)

    def search_count(self, model, domain):
        return self.call(model, "search_count", [domain])

    def fields_get(self, model, attributes):
        return self.call(model, "fields_get", [], {"attributes": attributes})
