"""Compose the complete gateway from reusable package functions.

This module contains the small amount of product-specific policy left after extracting program discovery, Dashboard communication, and declarative OPC UA
hosting into reusable packages. It selects local or SFTP discovery from ``Args``, binds the configured Dashboard endpoint, turns discovered program paths into
flat OPC UA method names, and defines the gateway's fixed namespace and robot object name.

``compose_gateway()`` is the main public API and returns a configured, unstarted server for ``_01_main`` to own. ``OPC_NAMESPACE`` is also public because OPC UA
clients and the system tests use it to resolve the application namespace. Generated method names are the only private application policy; backend selection
and protocol operations are supplied directly by reusable package functions.

The module depends on ``_02_parse_command_line_args``, ``declarative_opcua_server``, and the ``dashboard_client`` and ``urp_discovery_client`` modules from
``universal_robots_clients``. The reusable packages remain independent of this gateway; the discovery selector depends only on its two focused backends.
"""

import functools
import pathlib
import re
import typing

import declarative_opcua_server
import universal_robots_clients.dashboard_client as dashboard_client
import universal_robots_clients.urp_discovery_client as urp_discovery_client

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
    """Compose package operations into the configured gateway server.

    Used by ``_01_main.main()`` between argument parsing and process lifecycle management.
    """
    # Reuse one configured callable for startup method generation and the live ListPrograms method.
    discover_programs = functools.partial(
        urp_discovery_client.discover_programs,
        args.catalog,
        args.programs_folder,
        host=args.robot_host,
        username=args.sftp_username,
        password=args.robot_password,
        port=args.sftp_port,
        trust_unknown_host_keys=True,
    )
    programs = discover_programs()
    if len({_program_method_name(program) for program in programs}) != len(programs):
        raise ValueError("Discovered program paths produce duplicate OPC UA method names.")

    return declarative_opcua_server.create_server(
        status_interface={"ProgramState": functools.partial(dashboard_client.get_program_state, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT)},
        parameter_interface={},
        method_interface={
            "ListPrograms": discover_programs,
            "LoadProgram": functools.partial(dashboard_client.load_program, args.dashboard_host, port=args.dashboard_port, timeout=_DASHBOARD_TIMEOUT),
            "RunProgram": functools.partial(dashboard_client.play_program, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT),
            "PauseProgram": functools.partial(dashboard_client.pause_program, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT),
            "StopProgram": functools.partial(dashboard_client.stop_program, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT),
            **{
                _program_method_name(program): functools.partial(
                    dashboard_client.load_and_play_program, args.dashboard_host, program, args.dashboard_port, _DASHBOARD_TIMEOUT
                )
                for program in programs
            },
        },
        endpoint=args.opcua_endpoint,
        namespace=OPC_NAMESPACE,
        root_object=_ROOT_OBJECT,
    )
