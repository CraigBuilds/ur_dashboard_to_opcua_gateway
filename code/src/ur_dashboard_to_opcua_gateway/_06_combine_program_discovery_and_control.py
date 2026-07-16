"""Build the transport-independent application command model.

This module sits between concrete program operations and the OPC UA adapter. ``create_command_registry()`` combines a zero-argument discovery function with the
configured Dashboard functions under stable command names. ``create_program_shortcuts()`` runs discovery during gateway composition and creates bound ``load``
and ``run`` functions for every program, preserving directory paths for the presentation layer. A shortcut ``run`` currently performs load followed by play and
returns both raw Dashboard responses; response validation, atomicity, and cross-client serialization are planned beyond the MVP.

The public API also includes the ``Command``, ``CommandResult``, ``CommandRegistry``, and ``ProgramShortcuts`` type aliases that define the data exchanged with
the composition root and OPC UA module. Network access and OPC UA concepts are intentionally absent from this layer.

Its only package dependency is ``_05_control_ur_programs_via_dashboard`` for the Dashboard command dictionary type. Discovery is accepted as a callable instead
of imported directly, allowing the composition root to supply configured behaviour and keeping this module straightforward to test.
"""

import functools
import typing

import ur_dashboard_to_opcua_gateway._05_control_ur_programs_via_dashboard as control_ur_programs_via_dashboard

CommandResult = typing.Union[str, typing.List[str]]
Command = typing.Callable[..., CommandResult]
CommandRegistry = typing.Dict[str, Command]
ProgramShortcuts = typing.Dict[str, CommandRegistry]

__all__ = ["Command", "CommandRegistry", "CommandResult", "ProgramShortcuts", "create_command_registry", "create_program_shortcuts"]


def _run_program(load: Command, start: Command, program: str) -> str:
    """Load and then start one program."""
    loaded = load(program)
    started = start()

    return f"{loaded}; {started}"


def create_command_registry(
    discover_programs: typing.Callable[[], typing.List[str]], dashboard_commands: control_ur_programs_via_dashboard.DashboardCommands
) -> CommandRegistry:
    """Combine program discovery and Dashboard control into application commands.

    Used by ``_03_compose_gateway.compose_gateway()``.
    """
    return {"programs": discover_programs, **dashboard_commands}


def create_program_shortcuts(commands: CommandRegistry) -> ProgramShortcuts:
    """Create no-argument load and run commands for every discovered program.

    Used by ``_03_compose_gateway.compose_gateway()``.
    """
    result = commands["programs"]()

    if not isinstance(result, list):
        message = "The programs command must return a list."
        raise TypeError(message)

    load = commands["load"]
    start = commands["start"]
    shortcuts: ProgramShortcuts = {}

    for program in result:
        load_one = functools.partial(load, program)
        run_one = functools.partial(_run_program, load, start, program)
        shortcuts[program] = {"load": load_one, "run": run_one}

    return shortcuts
