"""Provide bounded polling for asynchronous container readiness."""

import time
import typing

Check = typing.Callable[[], bool]


def wait_until(check: Check, timeout: float, interval: float = 1.0) -> None:
    """Retry a condition until it succeeds or reaches a fixed deadline."""
    deadline = time.monotonic() + timeout
    last_error: typing.Optional[Exception] = None

    while time.monotonic() < deadline:
        try:
            if check():
                return
        except Exception as error:
            last_error = error

        time.sleep(interval)

    message = "Condition was not ready."

    if last_error is not None:
        raise TimeoutError(message) from last_error

    raise TimeoutError(message)
