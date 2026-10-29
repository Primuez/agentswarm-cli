"""Fixed exit codes, shared with the Node package and documented in README.md."""

from typing import Any, Optional

OK = 0
ERROR = 1
USAGE = 2
AUTH = 3
NOT_FOUND = 4
RATE_LIMITED = 5
SERVER = 6
NETWORK = 7
WAIT_TIMEOUT = 8

EXIT_CODES = {
    "OK": OK,
    "ERROR": ERROR,
    "USAGE": USAGE,
    "AUTH": AUTH,
    "NOT_FOUND": NOT_FOUND,
    "RATE_LIMITED": RATE_LIMITED,
    "SERVER": SERVER,
    "NETWORK": NETWORK,
    "WAIT_TIMEOUT": WAIT_TIMEOUT,
}


def exit_code_for_status(status: int) -> int:
    """Exit code for an HTTP error status."""
    if status in (401, 403):
        return AUTH
    if status == 404:
        return NOT_FOUND
    if status == 429:
        return RATE_LIMITED
    if 500 <= status <= 599:
        return SERVER
    return ERROR


class CliError(Exception):
    """An error that ends the command with a fixed exit code."""

    def __init__(
        self,
        code: int,
        message: str,
        status: Optional[int] = None,
        body: Any = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.body = body
        self.retry_after = retry_after


class UsageError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(USAGE, message)
