"""Send focused commands to a Universal Robots Dashboard Server.

Each protocol command opens one TCP connection, verifies the Dashboard greeting, sends exactly one newline-terminated command, reads one response, and closes
the connection. ``load_and_play_program()`` composes two of those command operations. Connection-per-command behavior keeps this first API stateless and makes
failures local to one exchange. Responses remain stripped text because Dashboard commands use different textual success and failure conventions that should
not be hidden behind premature result types.

The public API contains ``send_command()`` plus named program lifecycle operations: ``load_program()``, ``play_program()``, ``load_and_play_program()``,
``pause_program()``, ``stop_program()``, and ``get_program_state()``. All accept ordinary endpoint values and are reusable without gateway configuration
objects. Protocol framing and command validation remain private.

This module depends only on the standard-library ``socket`` and ``typing`` modules. It does not import program discovery, RTDE, OPC UA, or application policy.
"""

import socket
import typing

__all__ = ["get_program_state", "load_and_play_program", "load_program", "pause_program", "play_program", "send_command", "stop_program"]

DEFAULT_PORT = 29999
DEFAULT_TIMEOUT = 5.0
_TEXT_ENCODING = "utf-8"


def _validate_command(command: str) -> None:
    """Reject commands that could inject another Dashboard protocol line."""
    if "\n" in command or "\r" in command:
        raise ValueError("Command cannot contain line breaks.")


def _exchange(stream: typing.BinaryIO, command: str) -> bytes:
    """Exchange one complete Dashboard command through an open stream."""
    greeting = stream.readline()

    if not greeting:
        raise ConnectionError("No greeting received from the Dashboard Server.")

    stream.write(f"{command}\n".encode(_TEXT_ENCODING))
    stream.flush()
    response = stream.readline()

    if not response:
        raise ConnectionError("No response received from the Dashboard Server.")

    return response


def send_command(host: str, command: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Send one raw command and return its stripped Dashboard response.

    Used by the named operations in this module and by integration tools that need a Dashboard command not yet represented by a named helper.
    """
    _validate_command(command)
    connection = socket.create_connection((host, port), timeout)

    with connection:
        stream = connection.makefile("rwb")

        with stream:
            response = _exchange(stream, command)

    return response.decode(_TEXT_ENCODING, errors="replace").strip()


def load_program(host: str, program: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Load a URP program and return the raw Dashboard response.

    Used by applications that compose program invocation, including ``ur_dashboard_to_opcua_gateway``.
    """
    return send_command(host, f"load {program}", port, timeout)


def play_program(host: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Play the loaded program and return the raw Dashboard response.

    Used by applications that compose program invocation, including ``ur_dashboard_to_opcua_gateway``.
    """
    return send_command(host, "play", port, timeout)


def load_and_play_program(host: str, program: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Load one program, play it, and return the play response.

    Used by applications that expose one convenient operation per program, including ``ur_dashboard_to_opcua_gateway``.
    """
    load_program(host, program, port, timeout)

    return play_program(host, port, timeout)


def pause_program(host: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Pause the active program and return the raw Dashboard response.

    Used by applications that expose robot lifecycle commands, including ``ur_dashboard_to_opcua_gateway``.
    """
    return send_command(host, "pause", port, timeout)


def stop_program(host: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Stop the active program and return the raw Dashboard response.

    Used by applications that expose robot lifecycle commands, including ``ur_dashboard_to_opcua_gateway``.
    """
    return send_command(host, "stop", port, timeout)


def get_program_state(host: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Read the active program state as a raw Dashboard response.

    Used by applications that publish robot status, including ``ur_dashboard_to_opcua_gateway`` until its RTDE status source is implemented.
    """
    return send_command(host, "programState", port, timeout)
