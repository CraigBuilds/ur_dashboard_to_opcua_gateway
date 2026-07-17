"""Run the gateway process from configuration through clean shutdown.

This is the executable edge of the package and deliberately contains only process-level concerns. ``main()`` asks
``_02_parse_command_line_args`` for resolved configuration, passes it to ``_03_compose_gateway``, and then starts the returned OPC UA server. Keeping startup
here prevents signal handling and blocking process behaviour from leaking into the modules that implement gateway features.

The public API is ``main()``, which is used by both the installed ``ur_dashboard_to_opcua_gateway`` command and direct module execution. The internal
``_run_until_stopped()`` helper owns the server context manager, installs ``SIGINT`` and ``SIGTERM`` handlers, and waits on a threading event so the server is
closed normally when the process is asked to stop.

This module depends on the argument parser, the composition root, and Python's signal and threading facilities. The composed server's context-manager contract
keeps both ``asyncua`` and package-owned polling details out of the process entry point.
"""

import signal
import threading
import types
import typing

import ur_dashboard_to_opcua_gateway._02_parse_command_line_args as parse_command_line_args
import ur_dashboard_to_opcua_gateway._03_compose_gateway as compose_gateway

__all__ = ["main"]


def _run_until_stopped(server: typing.Any) -> None:
    """Run the composed server until the process receives a stop signal."""
    stopped = threading.Event()

    def request_stop(_number: int, _frame: typing.Optional[types.FrameType]) -> None:
        """Request a clean server shutdown."""
        stopped.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    with server:
        stopped.wait()


def main() -> None:
    """Start the gateway.

    Used by the ``ur_dashboard_to_opcua_gateway`` console script and direct module execution.
    """
    args = parse_command_line_args.parse_args()
    server = compose_gateway.compose_gateway(args)
    _run_until_stopped(server)


if __name__ == "__main__":
    main()
