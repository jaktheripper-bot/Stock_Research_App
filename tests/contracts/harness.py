"""Shared set-up for the contract tests: the real app, a real PostgreSQL, and no test-mode shortcuts.

What a ContractCase guarantees while its tests run:
- TESTING is NOT set, so the code takes its production branches (login, admin, paywall, payments).
- The database is a throwaway PostgreSQL (see pg_server.py), never SQLite and never production.
- Outbound network connections other than localhost are refused.
Sessions are created with the app's own signers, so the real cookie checks are what get exercised.
"""
import os
import socket
import unittest
from unittest.mock import patch

from tests.contracts import pg_server

# Test-only secrets for the app's own signers. Never real credentials.
TEST_ENV = {
    "TEST_SUPABASE": "1",
    "FORCE_LOCAL_SQLITE": "0",
    "ADMIN_PASSWORD": "contract-test-admin-password",
    "RAZORPAY_WEBHOOK_SECRET": "contract-test-webhook-secret",
    "ENVIRONMENT": "contract-test",
}
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _is_local(address) -> bool:
    if isinstance(address, (str, bytes)):  # unix socket path
        return True
    return bool(address) and str(address[0]) in _LOCAL_HOSTS


class ContractCase(unittest.TestCase):
    """Base class: real app, real Postgres, TESTING unset, no outbound network."""

    client = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        dsn = pg_server.dsn_or_none()
        if dsn is None:
            message = "No PostgreSQL available: install Homebrew postgresql or set MOATNOMICS_TEST_POSTGRES_DSN."
            if os.environ.get("CI"):
                raise RuntimeError(message)  # in CI a missing database is a failure, never a quiet skip
            raise unittest.SkipTest(message)

        cls._env = patch.dict(os.environ, {**TEST_ENV, "SUPABASE_DB_URL": dsn}, clear=False)
        cls._env.start()
        for name in ("TESTING", "SKIP_DOTENV_IN_SUBPROCESS", "ALLOW_PRODUCTION_DB"):
            os.environ.pop(name, None)

        real_connect = socket.socket.connect

        def guarded_connect(sock, address):
            if not _is_local(address):
                raise OSError(f"Contract tests may not reach the network: {address!r}")
            return real_connect(sock, address)

        cls._socket_patch = patch.object(socket.socket, "connect", guarded_connect)
        cls._socket_patch.start()

        import core.db.connection as db
        db._DB_INITIALIZED = False
        db._INITIALIZED_DBS.clear()
        db._SUPABASE_URL_RESOLVED = False
        db._PG_AVAILABLE = None
        db.init_db(force=True)

        from fastapi.testclient import TestClient
        from web.main import app
        cls.client = TestClient(app, base_url="http://localhost", follow_redirects=False)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "client", None) is not None:
            cls.client.close()
        for name in ("_socket_patch", "_env"):
            if hasattr(cls, name):
                getattr(cls, name).stop()
        super().tearDownClass()

    def assertRefused(self, response, msg=None):
        """A refusal is 401/403, or a redirect to a sign-in page, and never a 2xx with the protected body."""
        self.assertIn(response.status_code, (301, 302, 303, 307, 308, 401, 403), msg or response.text[:200])
