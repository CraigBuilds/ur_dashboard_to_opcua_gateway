"""Compose the complete gateway from reusable package functions.

This module contains the small amount of product-specific policy left after extracting program discovery, Dashboard communication, and declarative OPC UA
hosting into reusable packages. It selects local or SFTP discovery from ``Args``, binds the configured Dashboard endpoint, turns discovered program paths into
flat OPC UA method names, and defines the gateway's fixed namespace and robot object name.

``compose_gateway()`` is the main public API and returns a configured, unstarted server for ``_01_main`` to own. ``OPC_NAMESPACE`` is also public because OPC UA
clients and the system tests use it to resolve the application namespace. Generated method names are the only private application policy; backend selection
and protocol operations are supplied directly by reusable package functions.

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


def _program_method_name(program: str) -> str:
    """Convert a relative URP path into one deterministic flat method name."""
    path = pathlib.PurePosixPath(program)
    normalized = (re.sub(r"[^A-Za-z0-9]+", "_", part).strip("_") for part in path.with_suffix("").parts)
    meaningful = [part for part in normalized if part]

    if not meaningful:
        raise ValueError(f"Program path cannot produce a method name: {program!r}")

    return "StartProgram_" + "_".join(meaningful)


def compose_gateway(args: parse_command_line_args.Args) -> typing.Any:
    """Compose the configured gateway server.

    Used by ``_01_main.main()``.
    """
    discover_programs = functools.partial(
        program_discovery.discover_programs,
        args.catalog,
        args.programs_folder,
        args.robot_host,
        args.sftp_username,
        args.robot_password,
        args.sftp_port,
        program_discovery.DEFAULT_SFTP_TIMEOUT,
        True,
    )
    programs = discover_programs()
    if len({_program_method_name(program) for program in programs}) != len(programs):
        raise ValueError("Discovered program paths produce duplicate OPC UA method names.")

    return declarative_opcua_server.create_server(
        status_interface={"ProgramState": functools.partial(dashboard.get_program_state, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT)},
        parameter_interface={},
        method_interface={
            "ListPrograms": discover_programs,
            "LoadProgram": functools.partial(dashboard.load_program, args.dashboard_host, port=args.dashboard_port, timeout=_DASHBOARD_TIMEOUT),
            "RunProgram": functools.partial(dashboard.play_program, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT),
            "PauseProgram": functools.partial(dashboard.pause_program, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT),
            "StopProgram": functools.partial(dashboard.stop_program, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT),
            **{
                _program_method_name(program): functools.partial(
                    dashboard.load_and_play_program, args.dashboard_host, program, args.dashboard_port, _DASHBOARD_TIMEOUT
                )
                for program in programs
            },
        },
        endpoint=args.opcua_endpoint,
        namespace=OPC_NAMESPACE,
        root_object=_ROOT_OBJECT,
    )
