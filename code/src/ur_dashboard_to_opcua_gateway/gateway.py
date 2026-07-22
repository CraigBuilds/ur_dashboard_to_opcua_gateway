"""
This is the composition root of the package.
It is responsible for wiring together the gateway's configuration, discovery, ur_clients, and server components into one  server object.
It does not run the server; that is the responsibility of ``main.py``.
"""

import functools
import pathlib
import re
import typing

import declarative_opcua_server
import universal_robots_clients.dashboard_client as dashboard_client
import universal_robots_clients.urp_discovery_client as urp_discovery_client

import ur_dashboard_to_opcua_gateway.args as parse_command_line_args

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
    """Compose package operations into the configured gateway server."""

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

    # Call the callable to produce list of programs that will become opcua methods
    programs = discover_programs()
    if len({_program_method_name(program) for program in programs}) != len(programs):
        raise ValueError("Discovered program paths produce duplicate OPC UA method names.")

    # Create the opcua server
    return declarative_opcua_server.create_server(
        # Create read-only opcua nodes that poll dashboard_client.get_program_state to continuously update the program state node
        status_interface={"ProgramState": functools.partial(dashboard_client.get_program_state, args.dashboard_host, args.dashboard_port, _DASHBOARD_TIMEOUT)},
        # Create write-only opcua nodes that call the given callback whenever a client writes to them.
        parameter_interface={},
        # Create opcua methods that call the given callback whenever a client invokes them.
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
        # Create opcua server with the given endpoint, namespace, and root object name.
        endpoint=args.opcua_endpoint,
        namespace=OPC_NAMESPACE,
        root_object=_ROOT_OBJECT,
    )
