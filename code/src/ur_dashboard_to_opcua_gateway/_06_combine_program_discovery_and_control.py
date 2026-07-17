"""Build the transport-independent application command model.

This module sits between concrete program operations and the OPC UA adapter. ``create_command_registry()`` combines a zero-argument discovery function with the
configured Dashboard functions under stable command names. It also runs discovery during gateway composition and creates bound ``load`` and ``run`` functions
for every program, preserving directory paths for the presentation layer. A per-program ``run`` currently performs load followed by play and returns both raw
Dashboard responses; response validation, atomicity, and cross-client serialization are planned beyond the MVP.

The public API consists of ``create_command_registry()`` and the ``Command``, ``CommandResult``, and ``CommandRegistry`` types that describe its result. The
registry is one application model containing generic commands and per-program operations. Network access and OPC UA concepts are intentionally absent from this
layer.

Its only package dependency is ``_05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde`` for the Dashboard command dictionary type. Discovery
is accepted as a callable instead of imported directly, allowing the composition root to supply configured behaviour and keeping this module straightforward to
test.
"""

import dataclasses
import functools
import typing

import ur_dashboard_to_opcua_gateway._05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde as control_ur_programs_and_exchange_parameters

CommandResult = typing.Union[str, typing.List[str]]
Command = typing.Callable[..., CommandResult]
_Commands = typing.Dict[str, Command]
_ProgramOperations = typing.Dict[str, _Commands]


@dataclasses.dataclass(frozen=True)
class CommandRegistry:
    """Hold all transport-independent commands exposed by the gateway.

    Used by ``_03_compose_gateway.compose_gateway()`` and
    ``_07_expose_program_commands_via_opcua.create_server()``.
    """

    commands: _Commands
    program_operations: _ProgramOperations


__all__ = ["Command", "CommandRegistry", "CommandResult", "create_command_registry"]


def _run_program(load: Command, start: Command, program: str) -> str:
    """Load and then start one program."""
    loaded = load(program)
    started = start()

    return f"{loaded}; {started}"


def create_command_registry(
    discover_programs: typing.Callable[[], typing.List[str]], dashboard_commands: control_ur_programs_and_exchange_parameters.DashboardCommands
) -> CommandRegistry:
    """Build the complete application command model.

    Used by ``_03_compose_gateway.compose_gateway()``.
    """
    commands: _Commands = {"programs": discover_programs, **dashboard_commands}

    return CommandRegistry(commands=commands, program_operations=_create_program_operations(commands))


def _create_program_operations(commands: _Commands) -> _ProgramOperations:
    """Create no-argument load and run commands for every discovered program."""
    result = commands["programs"]()

    if not isinstance(result, list):
        message = "The programs command must return a list."
        raise TypeError(message)

    load = commands["load"]
    start = commands["start"]
    program_operations: _ProgramOperations = {}

    for program in result:
        load_one = functools.partial(load, program)
        run_one = functools.partial(_run_program, load, start, program)
        program_operations[program] = {"load": load_one, "run": run_one}

    return program_operations
