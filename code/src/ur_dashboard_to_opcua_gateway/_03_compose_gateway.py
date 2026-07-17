"""Compose the complete gateway from reusable package functions.

This module contains the small amount of product-specific policy left after extracting program discovery, Dashboard communication, and declarative OPC UA
hosting into reusable packages. It selects local or SFTP discovery from ``Args``, binds the configured Dashboard endpoint, turns discovered program paths into
flat OPC UA method names, and defines the gateway's fixed namespace and robot object name.

``compose_gateway()`` is the main public API and returns a configured, unstarted server for ``_01_main`` to own. ``OPC_NAMESPACE`` is also public because OPC UA
clients and the system tests use it to resolve the application namespace. Discovery selection, load-then-play behavior, command-response adaptation, and method
name generation are intentionally private application details.

The module depends on ``_02_parse_command_line_args``, ``declarative_opcua_server``, and the ``dashboard`` and ``program_discovery`` modules from
``universal_robots_clients``. The reusable packages remain independent of this gateway and of one another.
"""

import functools
import pathlib
import re
import typing

import declarative_opcua_server
import universal_robots_clients.dashboard as dashboard
import universal_robots_clients.program_discovery as program_discovery

import ur_dashboard_to_opcua_gateway._02_parse_command_line_args as parse_command_line_args

__all__ = ["OPC_NAMESPACE", "compose_gateway"]

OPC_NAMESPACE = "urn:ur20:program-control"
_ROOT_OBJECT = "UR20"
_DASHBOARD_TIMEOUT = 5.0
_DashboardCommand = typing.Callable[..., str]


def _discover_programs(args: parse_command_line_args.Args) -> typing.List[str]:
    """Discover programs through the configured reusable package operation."""
    if args.catalog == "local":
        return program_discovery.discover_local_programs(args.programs_folder)

    if args.catalog != "sftp":
        raise ValueError(f"Unsupported catalogue: {args.catalog}")

    if args.robot_host is None:
        raise ValueError("Robot host is required for SFTP discovery.")

    if args.robot_password is None:
        raise ValueError("Robot password is required for SFTP discovery.")

    return program_discovery.discover_programs_over_sftp(
        host=args.robot_host,
        root=args.programs_folder,
        username=args.sftp_username,
        password=args.robot_password,
        port=args.sftp_port,
        trust_unknown_host_keys=True,
    )


def _run_program(args: parse_command_line_args.Args, program: str) -> None:
    """Load and then play one discovered program."""
    dashboard.load_program(args.dashboard_host, program, args.dashboard_port, _DASHBOARD_TIMEOUT)
    dashboard.play_program(args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT)


def _run_command(command: _DashboardCommand, args: parse_command_line_args.Args) -> None:
    """Expose one response-returning Dashboard operation as a no-result method."""
    command(args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT)


def _program_method_name(program: str) -> str:
    """Convert a relative URP path into one deterministic flat method name."""
    path = pathlib.PurePosixPath(program)
    normalized = (re.sub(r"[^A-Za-z0-9]+", "_", part).strip("_") for part in path.with_suffix("").parts)
    meaningful = [part for part in normalized if part]

    if not meaningful:
        raise ValueError(f"Program path cannot produce a method name: {program!r}")

    return "StartProgram_" + "_".join(meaningful)


def _create_method_interface(args: parse_command_line_args.Args, programs: typing.Sequence[str]) -> typing.Dict[str, typing.Callable[[], None]]:
    """Create program-specific and robot-wide OPC UA method functions."""
    methods = {_program_method_name(program): functools.partial(_run_program, args, program) for program in programs}

    if len(methods) != len(programs):
        raise ValueError("Discovered program paths produce duplicate OPC UA method names.")

    methods["PauseProgram"] = functools.partial(_run_command, dashboard.pause_program, args)
    methods["StopProgram"] = functools.partial(_run_command, dashboard.stop_program, args)

    return methods


def compose_gateway(args: parse_command_line_args.Args) -> typing.Any:
    """Compose the configured gateway server.

    Used by ``_01_main.main()``.
    """
    status_interface = {"ProgramState": functools.partial(dashboard.get_program_state, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT)}
    method_interface = _create_method_interface(args, _discover_programs(args))

    return declarative_opcua_server.create_server(
        status_interface=status_interface,
        parameter_interface={},
        method_interface=method_interface,
        endpoint=args.opcua_endpoint,
        namespace=OPC_NAMESPACE,
        root_object=_ROOT_OBJECT,
    )
