"""Shared read-only Odoo client guarantees, with XML-RPC mocked (no network, no .env)."""

import unittest
from unittest import mock

from odoo_client import OdooAccessError, OdooClient


class ReadOnlyClientTests(unittest.TestCase):
    def make_client(self, proxy_cls, uid=2):
        proxy = proxy_cls.return_value
        proxy.authenticate.return_value = uid
        return OdooClient("https://odoo.invalid", "db", "login", "secret"), proxy

    @mock.patch("odoo_client.xmlrpc.client.ServerProxy")
    def test_only_read_methods_reach_odoo_and_failures_become_access_errors(self, proxy_cls):
        client, proxy = self.make_client(proxy_cls)

        client.search_count("res.partner", [])
        self.assertEqual(proxy.execute_kw.call_count, 1)

        for method in ("create", "write", "unlink"):
            with self.subTest(method=method):
                with self.assertRaises(ValueError):
                    client.call("res.partner", method, [])
        self.assertEqual(proxy.execute_kw.call_count, 1)  # refused before any request

        proxy.execute_kw.side_effect = RuntimeError("boom")
        with self.assertRaises(OdooAccessError):
            client.search_read("res.partner", [], ["name"])

    @mock.patch("odoo_client.xmlrpc.client.ServerProxy")
    def test_rejected_login_is_an_access_error(self, proxy_cls):
        with self.assertRaises(OdooAccessError):
            self.make_client(proxy_cls, uid=False)


if __name__ == "__main__":
    unittest.main()
