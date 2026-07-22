"""
Run the gateway process from configuration through clean shutdown.
This is the executable edge of the package and deliberately contains only process-level concerns. ``main()`` asks
``args.py`` for resolved configuration, passes it to ``gateway.py``, and then starts the returned OPC UA server.
"""

import signal
import threading
import types
import typing

import ur_dashboard_to_opcua_gateway.args as parse_command_line_args
import ur_dashboard_to_opcua_gateway.gateway as compose_gateway

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
    """Start the gateway"""
    args = parse_command_line_args.parse_args()
    server = compose_gateway.compose_gateway(args)
    _run_until_stopped(server)


if __name__ == "__main__":
    main()
