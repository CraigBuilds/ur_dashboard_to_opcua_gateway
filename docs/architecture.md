# Architecture

## Source reading order

The production modules are named for the activity they perform. Reading them in numeric order follows the gateway from process entry through configuration,
composition, program discovery, robot control, command combination, and OPC UA exposure.

```text
_01_main.py
    Parse configuration, compose the gateway, and own process startup and shutdown.

_02_parse_command_line_args.py
    Parse and validate command-line and environment configuration into Args.

_03_compose_gateway.py
    Assemble the configured dependencies and return the OPC UA server.

_04_discover_ur_programs.py
    Discover UR programs from a local directory or SFTP.

_05_control_ur_programs_via_dashboard.py
    Control UR programs through the Universal Robots Dashboard Server.

_06_combine_program_discovery_and_control.py
    Combine program discovery and Dashboard control into application commands.

_07_expose_program_commands_via_opcua.py
    Expose the application commands through an OPC UA address space.
```

The numeric prefixes are part of the module names and keep the intended reading order visible in an alphabetical file listing.

## Dependencies

```text
_01_main
    +-- _02_parse_command_line_args
    +-- _03_compose_gateway

_03_compose_gateway
    +-- _02_parse_command_line_args
    +-- _04_discover_ur_programs
    +-- _05_control_ur_programs_via_dashboard
    +-- _06_combine_program_discovery_and_control
    +-- _07_expose_program_commands_via_opcua

_04_discover_ur_programs
    +-- _02_parse_command_line_args

_05_control_ur_programs_via_dashboard
    +-- _02_parse_command_line_args

_06_combine_program_discovery_and_control
    +-- _05_control_ur_programs_via_dashboard

_07_expose_program_commands_via_opcua
    +-- _06_combine_program_discovery_and_control
```

The graph is acyclic. `_02_parse_command_line_args` does not import later application modules, while `_03_compose_gateway` is the composition root and is the
only module that imports every concrete component.

## Public module APIs

Each module declares its cross-module API in `__all__`. Functions, constants, and type aliases that begin with an underscore are module-internal implementation
details. Public function and dataclass docstrings identify the modules that use them.

```text
_01_main
    main

_02_parse_command_line_args
    Args
    parse_args

_03_compose_gateway
    compose_gateway

_04_discover_ur_programs
    discover_programs

_05_control_ur_programs_via_dashboard
    DashboardCommand
    DashboardCommands
    create_dashboard_commands
    send_command

_06_combine_program_discovery_and_control
    Command
    CommandRegistry
    CommandResult
    ProgramShortcuts
    create_command_registry
    create_program_shortcuts

_07_expose_program_commands_via_opcua
    OPC_NAMESPACE
    create_server
```

`Args` is the only class declared in production code, and it is an immutable dataclass. Program discovery is exposed as one function that accepts `Args`. The
composition root binds those arguments into the zero-argument function required by the command registry. Dashboard control is represented by configured
functions in a `DashboardCommands` dictionary. Local discovery, SFTP discovery, Dashboard protocol exchange, OPC UA argument conversion, folder creation, and
callback adaptation remain internal functions.

The container-backed test harness still uses classes where object identity and resource lifecycles are useful.

Cross-module calls retain their module namespace:

```python
import functools

import ur_dashboard_to_opcua_gateway._04_discover_ur_programs as discover_ur_programs
import ur_dashboard_to_opcua_gateway._05_control_ur_programs_via_dashboard as control_ur_programs_via_dashboard

discover_programs_function = functools.partial(discover_ur_programs.discover_programs, args)
dashboard_commands = control_ur_programs_via_dashboard.create_dashboard_commands(args)
```

`tests/test_namespace_imports.py` enforces module docstrings, namespace imports, consumer documentation for public callables, and the rule that production
classes are reserved for dataclasses.

## Runtime flow

```text
_01_main.main()
    -> _02_parse_command_line_args.parse_args()
    -> _03_compose_gateway.compose_gateway()
    -> _01_main._run_until_stopped()

_03_compose_gateway.compose_gateway()
    -> functools.partial(_04_discover_ur_programs.discover_programs, args)
    -> _05_control_ur_programs_via_dashboard.create_dashboard_commands()
    -> _06_combine_program_discovery_and_control.create_command_registry()
    -> _06_combine_program_discovery_and_control.create_program_shortcuts()
    -> _07_expose_program_commands_via_opcua.create_server()
```

`_03_compose_gateway` constructs and returns the server without starting it. `_01_main` owns `SIGINT` and `SIGTERM`, starts the server through its context
manager, waits for a stop request, and lets the context manager close the server.

The composition root configures program discovery with `functools.partial`, while the Dashboard factory returns configured functions rather than state-holder
objects. Program discovery runs during composition to generate shortcuts and runs again whenever a client calls the generic `programs()` command. The combined
application commands remain independent of OPC UA, so other transports can be added without changing discovery or Dashboard control.

## Repository layout

```text
.github/workflows/ci.yml
code/
    Dockerfile
    pyproject.toml
    src/ur_dashboard_to_opcua_gateway/
docs/
tests/
```

`code/pyproject.toml` is the single source of package and dependency metadata. Generated caches, egg metadata, and built distributions are intentionally absent.

## Python compatibility

The package supports Python 3.8.3 and later. Runtime annotations use `typing` forms that are evaluated correctly on Python 3.8, and the namespace-import tests
avoid syntax and standard-library helpers introduced in later Python releases.

Dependency markers select `asyncua` 1.1.5 on Python 3.8 and 3.9 and `asyncua` 2.0.1 on Python 3.10 and later. CI runs unit tests on Python 3.8.3 and 3.12,
formatting on Python 3.8.3, and Docker-backed system tests on Python 3.12. The local system-test runner accepts Python 3.10 or later because its current
`testcontainers` dependency does not support older versions. The deployment Docker image also remains on Python 3.12.
