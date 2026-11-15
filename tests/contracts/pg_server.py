"""A throwaway PostgreSQL for the contract tests.

CI provides one through MOATNOMICS_TEST_POSTGRES_DSN. On a laptop with Homebrew PostgreSQL this module
starts a temporary server on a random local port, in a scratch folder, and deletes it when the test run
ends. It never reads .env, never uses a production address and never touches reports.db.
"""
import atexit
import glob
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

ENV_DSN = "MOATNOMICS_TEST_POSTGRES_DSN"
DB_NAME = "moatnomics_contract_test"
_BIN_GLOBS = ("/opt/homebrew/opt/postgresql@*/bin", "/usr/local/opt/postgresql@*/bin", "/usr/lib/postgresql/*/bin")

_server = None


def _bin(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    for pattern in _BIN_GLOBS:
        for directory in sorted(glob.glob(pattern), reverse=True):
            candidate = Path(directory) / name
            if candidate.exists():
                return str(candidate)
    return None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ThrowawayPostgres:
    def __init__(self) -> None:
        self.root = tempfile.mkdtemp(prefix="moatnomics_pg_")
        self.port = _free_port()
        self.dsn = f"postgresql://postgres@127.0.0.1:{self.port}/{DB_NAME}"
        self._started = False

    def start(self) -> None:
        initdb, pg_ctl = _bin("initdb"), _bin("pg_ctl")
        data = os.path.join(self.root, "data")
        subprocess.run([initdb, "-D", data, "-U", "postgres", "--auth=trust", "-E", "UTF8"],
                       check=True, capture_output=True)
        options = f"-p {self.port} -h 127.0.0.1 -k {self.root} -c fsync=off -c synchronous_commit=off"
        subprocess.run([pg_ctl, "-D", data, "-o", options, "-l", os.path.join(self.root, "pg.log"), "-w", "start"],
                       check=True, capture_output=True)
        self._started = True
        import psycopg2
        admin = psycopg2.connect(host="127.0.0.1", port=self.port, user="postgres", dbname="postgres")
        admin.autocommit = True
        try:
            admin.cursor().execute(f"CREATE DATABASE {DB_NAME}")
        finally:
            admin.close()

    def stop(self) -> None:
        if self._started:
            subprocess.run([_bin("pg_ctl"), "-D", os.path.join(self.root, "data"), "-m", "immediate", "stop"],
                           capture_output=True)
            self._started = False
        shutil.rmtree(self.root, ignore_errors=True)


def dsn_or_none() -> Optional[str]:
    """The DSN of the test Postgres: CI's, or a throwaway one started on first use. None if unavailable."""
    global _server
    explicit = os.environ.get(ENV_DSN, "").strip()
    if explicit:
        if "test" not in explicit.lower():
            raise RuntimeError(f"Refusing {ENV_DSN}: the address must identify a dedicated test database.")
        return explicit
    if _server is not None:
        return _server.dsn
    if not (_bin("initdb") and _bin("pg_ctl")):
        return None
    server = ThrowawayPostgres()
    atexit.register(server.stop)
    server.start()
    _server = server
    return server.dsn
