"""Bind reusable robot clients into gateway-ready control and data functions.

This application adapter currently binds the configured Dashboard host and port to the reusable operations in ``universal_robots_clients.dashboard``. The
resulting flat function mapping has one argument-taking loader plus zero-argument play, pause, stop, and state functions, making it straightforward for the next
module to create gateway methods and status getters without carrying connection configuration further through the application.

RTDE parameter exchange remains deliberately absent until a real client and robot-side register contract have been selected and tested. When that work lands,
this module will bind reusable ``universal_robots_clients.rtde`` operations into status getters and parameter setters without moving invocation policy into the
client package. The OPC UA package already accepts those callable shapes.

The public API is ``create_dashboard_commands()`` and its two callable mapping aliases. This module depends on ``Args`` and
``universal_robots_clients.dashboard``. It does not implement sockets, OPC UA nodes, program discovery, or cross-protocol workflow policy.
"""

import functools
import typing

import universal_robots_clients.dashboard as dashboard

import ur_dashboard_to_opcua_gateway._02_parse_command_line_args as parse_command_line_args

DashboardCommand = typing.Callable[..., str]
DashboardCommands = typing.Dict[str, DashboardCommand]

__all__ = ["DashboardCommand", "DashboardCommands", "create_dashboard_commands"]

_DASHBOARD_TIMEOUT = 5.0


def _load_program(args: parse_command_line_args.Args, program: str) -> str:
    """Load one program through the configured Dashboard endpoint."""
    return dashboard.load_program(args.dashboard_host, program, args.dashboard_port, _DASHBOARD_TIMEOUT)


def _play_program(args: parse_command_line_args.Args) -> str:
    """Play the configured robot's loaded program."""
    return dashboard.play_program(args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT)


def _pause_program(args: parse_command_line_args.Args) -> str:
    """Pause the configured robot's active program."""
    return dashboard.pause_program(args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT)


def _stop_program(args: parse_command_line_args.Args) -> str:
    """Stop the configured robot's active program."""
    return dashboard.stop_program(args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT)


def _get_program_state(args: parse_command_line_args.Args) -> str:
    """Read the configured robot's program state."""
    return dashboard.get_program_state(args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT)


def create_dashboard_commands(args: parse_command_line_args.Args) -> DashboardCommands:
    """Create configured Dashboard functions for gateway composition.

    Used by ``_03_compose_gateway.compose_gateway()``.
    """
    return {
        "load_program": functools.partial(_load_program, args),
        "play_program": functools.partial(_play_program, args),
        "pause_program": functools.partial(_pause_program, args),
        "stop_program": functools.partial(_stop_program, args),
        "get_program_state": functools.partial(_get_program_state, args),
    }
