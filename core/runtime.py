"""One shared answer to "is this process a test run?".

`core/config.py`, `core/notify.py` and `core/db/connection.py` each had their own version, and they
disagreed: a test file run directly (`python tests/unit/test_x.py`) or a process with pytest loaded
was a test to the email guard but not to the database selector. This module is the single
definition; it imports nothing from the project so any module can use it.
"""

import os
import sys

_TEST_RUNNERS = ("unittest", "pytest")


def _entrypoint_is_test(argv0: str) -> bool:
    normalised = argv0.replace("\\", "/")
    if any(runner in normalised for runner in _TEST_RUNNERS):
        return True
    # A test file run directly, for example `python tests/unit/test_x.py`.
    return normalised.startswith("tests/") or "/tests/" in normalised


def is_test_runtime() -> bool:
    """True under unittest/pytest, a directly-run test file, or an isolated test subprocess."""
    argv0 = sys.argv[0] if sys.argv else ""
    return (
        os.environ.get("TESTING") == "1"
        or os.environ.get("ENVIRONMENT") == "testing"
        or os.environ.get("SKIP_DOTENV_IN_SUBPROCESS") == "1"
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
        or "pytest" in sys.modules
        or _entrypoint_is_test(argv0)
    )
