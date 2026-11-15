"""Contract: admin endpoints refuse anyone without a real admin session.

Rule (OWASP ASVS 4.1.1, enforce access control on a trusted server-side layer): whether a request is
admin must come from its credentials, never from what happens to be loaded in the server process.
Escape this guards against: web/routers/admin.py treated `"pytest" in sys.modules` as permission.
"""
import sys
import types
import unittest
from unittest.mock import patch

from tests.contracts.harness import ContractCase

ADMIN_READ_ENDPOINTS = ("/api/admin/audit-logs", "/api/admin/project-audit-status/does-not-exist")


class TestAdminRefusesAnonymous(ContractCase):
    def test_anonymous_is_refused(self):
        for path in ADMIN_READ_ENDPOINTS:
            with self.subTest(path=path):
                self.assertRefused(self.client.get(path))

    def test_pytest_being_loaded_grants_nothing(self):
        """Simulates a server process that has imported pytest, e.g. through a dependency."""
        with patch.dict(sys.modules, {"pytest": types.ModuleType("pytest")}):
            for path in ADMIN_READ_ENDPOINTS:
                with self.subTest(path=path):
                    self.assertRefused(self.client.get(path))

    def test_made_up_admin_headers_and_cookies_are_refused(self):
        headers = {"x-admin-key": "not-the-key", "x-unlock-preview": "1"}
        for path in ADMIN_READ_ENDPOINTS:
            with self.subTest(path=path):
                response = self.client.get(path, headers=headers, cookies={"admin_session": "forged"})
                self.assertRefused(response)


if __name__ == "__main__":
    unittest.main()
