"""Combine discovery and robot control into the gateway's three flat interfaces.

``create_interfaces()`` discovers programs during composition and creates one no-argument start method for each program. It also adds robot-wide pause and stop
methods, publishes the Dashboard program state as a status getter, and leaves the parameter interface empty until the RTDE invocation contract is implemented.
All names are flat because the declarative OPC UA package supplies the fixed ``Status``, ``Parameters``, and ``Methods`` containers.

Program start functions implement the gateway-specific load-then-play policy while reusable Dashboard functions remain protocol primitives. Program paths are
converted into deterministic method names such as ``StartProgram_Production_PickPart``; collisions are rejected instead of silently losing a program during
dictionary construction.

The public API consists of the immutable ``GatewayInterfaces`` dataclass and ``create_interfaces()``. This module accepts ordinary functions and mappings, so it
does not import discovery, Dashboard, RTDE, OPC UA, or command-line modules. The composition root supplies all concrete dependencies.
"""

import dataclasses
import functools
import pathlib
import re
import typing

_Command = typing.Callable[..., str]
_DashboardCommands = typing.Mapping[str, _Command]
_MethodFunction = typing.Callable[[], None]
_StatusFunction = typing.Callable[[], typing.Any]
_ParameterFunction = typing.Callable[..., None]
_MethodInterface = typing.Dict[str, _MethodFunction]
_StatusInterface = typing.Dict[str, _StatusFunction]
_ParameterInterface = typing.Dict[str, _ParameterFunction]

__all__ = ["GatewayInterfaces", "create_interfaces"]


@dataclasses.dataclass(frozen=True)
class GatewayInterfaces:
    """Hold the flat status, parameter, and method interfaces exposed by OPC UA.

    Used by ``_03_compose_gateway.compose_gateway()`` and ``_07_expose_program_commands_via_opcua.create_server()``.
    """

    status_interface: _StatusInterface
    parameter_interface: _ParameterInterface
    method_interface: _MethodInterface


def _run_program(load_program: _Command, play_program: _Command, program: str) -> None:
    """Load and then play one discovered program."""
    load_program(program)
    play_program()


def _run_command(command: _Command) -> None:
    """Run one response-returning Dashboard command as a no-result method."""
    command()


def _program_method_name(program: str) -> str:
    """Convert a relative URP path into one deterministic flat method name."""
    path = pathlib.PurePosixPath(program)
    parts = path.with_suffix("").parts
    normalized = (re.sub(r"[^A-Za-z0-9]+", "_", part).strip("_") for part in parts)
    meaningful = [part for part in normalized if part]

    if not meaningful:
        raise ValueError(f"Program path cannot produce a method name: {program!r}")

    return "StartProgram_" + "_".join(meaningful)


def create_interfaces(discover_programs: typing.Callable[[], typing.List[str]], dashboard_commands: _DashboardCommands) -> GatewayInterfaces:
    """Create the complete flat gateway interfaces from configured dependencies.

    Used by ``_03_compose_gateway.compose_gateway()``.
    """
    programs = discover_programs()
    load_program = dashboard_commands["load_program"]
    play_program = dashboard_commands["play_program"]
    program_methods = {_program_method_name(program): functools.partial(_run_program, load_program, play_program, program) for program in programs}

    if len(program_methods) != len(programs):
        raise ValueError("Discovered program paths produce duplicate OPC UA method names.")

    method_interface: _MethodInterface = {
        **program_methods,
        "PauseProgram": functools.partial(_run_command, dashboard_commands["pause_program"]),
        "StopProgram": functools.partial(_run_command, dashboard_commands["stop_program"]),
    }
    status_interface: _StatusInterface = {"ProgramState": dashboard_commands["get_program_state"]}

    return GatewayInterfaces(status_interface=status_interface, parameter_interface={}, method_interface=method_interface)
