"""Assemble the gateway's concrete dependencies without starting the process.

This module is the composition root: the one place that knows every feature module and connects them in runtime order. It binds ``Args`` to program discovery
with ``functools.partial``, creates Dashboard command functions, combines both sets of operations into the application command registry, generates per-program
shortcuts, and asks the OPC UA adapter to expose the result.

The sole public API is ``compose_gateway(args)``. It returns a fully configured but unstarted synchronous ``asyncua`` server; ``_01_main`` remains responsible
for entering the server context, waiting for process signals, and shutting it down. This separation makes composition independently testable and keeps lifecycle
policy out of the application modules.

Dependencies flow from this module to ``_02_parse_command_line_args`` and each feature module from ``_04`` through ``_07``. Those modules do not import the
composition root, so concrete wiring remains centralized and the rest of the codebase can stay focused on one concern at a time.
"""

import functools

import asyncua.sync

import ur_dashboard_to_opcua_gateway._02_parse_command_line_args as parse_command_line_args
import ur_dashboard_to_opcua_gateway._04_discover_ur_programs as discover_ur_programs
import ur_dashboard_to_opcua_gateway._05_control_ur_programs_via_dashboard as control_ur_programs_via_dashboard
import ur_dashboard_to_opcua_gateway._06_combine_program_discovery_and_control as combine_program_discovery_and_control
import ur_dashboard_to_opcua_gateway._07_expose_program_commands_via_opcua as expose_program_commands_via_opcua

__all__ = ["compose_gateway"]


def compose_gateway(args: parse_command_line_args.Args) -> asyncua.sync.Server:
    """Compose and return the configured gateway server.

    Used by ``_01_main.main()``.
    """
    discover_programs_function = functools.partial(discover_ur_programs.discover_programs, args)
    dashboard_commands = control_ur_programs_via_dashboard.create_dashboard_commands(args)
    commands = combine_program_discovery_and_control.create_command_registry(discover_programs_function, dashboard_commands)
    shortcuts = combine_program_discovery_and_control.create_program_shortcuts(commands)

    return expose_program_commands_via_opcua.create_server(commands, shortcuts, args.opcua_endpoint)
