"""Provide configured functions for Universal Robots Dashboard operations.

This module is the robot-control adapter. It implements the Dashboard Server's line-oriented TCP exchange and presents ordinary Python callables for loading,
starting, pausing, stopping, and querying a program. Each invocation validates that the command cannot inject another protocol line, opens a connection, reads
the server greeting, sends one newline-terminated command, reads one response, and closes the connection. Responses remain stripped text in the MVP rather than
being interpreted as typed success or failure values.

The public API includes the ``DashboardCommand`` and ``DashboardCommands`` callable types, low-level ``send_command()``, and
``create_dashboard_commands(args)``. The factory binds the configured host, port, and timeout into a dictionary whose function signatures are suitable for the
application registry and OPC UA method generation. Command-specific formatting and socket exchange helpers remain internal.

This module depends on ``Args`` from ``_02_parse_command_line_args`` and Python's ``socket`` and ``functools`` modules. It does not depend on discovery, command
combination, or OPC UA, which keeps the Dashboard protocol usable and testable on its own.
"""

import functools
import socket
import typing

import ur_dashboard_to_opcua_gateway._02_parse_command_line_args as parse_command_line_args

DashboardCommand = typing.Callable[..., str]
DashboardCommands = typing.Dict[str, DashboardCommand]

__all__ = ["DashboardCommand", "DashboardCommands", "create_dashboard_commands", "send_command"]

_DASHBOARD_TIMEOUT = 5.0
_TEXT_ENCODING = "utf-8"


def _exchange(stream: typing.BinaryIO, command: str) -> bytes:
    """Exchange one Dashboard command."""
    greeting = stream.readline()

    if not greeting:
        message = "No greeting received."
        raise ConnectionError(message)

    line = f"{command}\n"
    data = line.encode(_TEXT_ENCODING)
    stream.write(data)
    stream.flush()

    response = stream.readline()

    if not response:
        message = "No response received."
        raise ConnectionError(message)

    return response


def _validate_command(command: str) -> None:
    """Reject commands with line breaks."""
    has_newline = "\n" in command
    has_return = "\r" in command

    if has_newline or has_return:
        message = "Command cannot contain line breaks."
        raise ValueError(message)


def send_command(host: str, port: int, command: str, timeout: float = _DASHBOARD_TIMEOUT) -> str:
    """Send one command to a UR Dashboard Server.

    Used by command functions in this module and ``tests.containers.ursim_container``.
    """
    _validate_command(command)
    address = (host, port)
    connection = socket.create_connection(address, timeout)

    with connection:
        stream = connection.makefile("rwb")

        with stream:
            response = _exchange(stream, command)

    text = response.decode(_TEXT_ENCODING, errors="replace")

    return text.strip()


def _load_program(host: str, port: int, timeout: float, program: str) -> str:
    """Load one robot program."""
    command = f"load {program}"

    return send_command(host, port, command, timeout)


def _play_program(host: str, port: int, timeout: float) -> str:
    """Start the loaded program."""
    return send_command(host, port, "play", timeout)


def _pause_program(host: str, port: int, timeout: float) -> str:
    """Pause the running program."""
    return send_command(host, port, "pause", timeout)


def _stop_program(host: str, port: int, timeout: float) -> str:
    """Stop the active program."""
    return send_command(host, port, "stop", timeout)


def _get_program_state(host: str, port: int, timeout: float) -> str:
    """Return the active program state."""
    return send_command(host, port, "programState", timeout)


def create_dashboard_commands(args: parse_command_line_args.Args) -> DashboardCommands:
    """Create configured functions that control UR programs through Dashboard.

    Used by ``_03_compose_gateway.compose_gateway()``.
    """
    endpoint = (args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT)

    return {
        "load": functools.partial(_load_program, *endpoint),
        "start": functools.partial(_play_program, *endpoint),
        "pause": functools.partial(_pause_program, *endpoint),
        "stop": functools.partial(_stop_program, *endpoint),
        "status": functools.partial(_get_program_state, *endpoint),
    }
