# Architecture

## Overview

The repository now contains three independently installable Python distributions:

```text
ur_dashboard_to_opcua_gateway
    +-- declarative-opcua-server
    |       +-- asyncua
    +-- universal-robots-clients
            +-- Python standard library
            +-- paramiko [optional SFTP extra]
```

The package projects do not depend on one another. The gateway is the only layer that combines robot clients with OPC UA.

## Gateway reading order

```text
_01_main.py
    Parse configuration, compose the gateway, and own process startup and shutdown.

_02_parse_command_line_args.py
    Resolve command-line, environment, default, and validation rules into Args.

_03_compose_gateway.py
    Bind concrete discovery and Dashboard functions and return the configured server.

_04_discover_ur_programs.py
    Select local or SFTP package discovery from Args.

_05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde.py
    Bind reusable Dashboard operations and reserve the application boundary for RTDE.

_06_combine_program_discovery_and_control.py
    Create flat status, parameter, and method interfaces from configured functions.

_07_expose_program_commands_via_opcua.py
    Apply the gateway namespace, endpoint, and UR20 root to the declarative server.
```

The numeric prefixes keep the intended reading order visible in an alphabetical listing.

## Package responsibilities

### declarative-opcua-server

The package exposes only `declarative_opcua_server.create_server()`. It receives three flat mappings:

```python
server = declarative_opcua_server.create_server(
    status_interface={"ToolVoltage": read_tool_voltage},
    parameter_interface={"TargetHeight": write_target_height},
    method_interface={"StartRoutine": start_routine},
)
```

Its fixed address space is:

```text
Application/
    Status/       typed zero-argument getters, polled and read-only
    Parameters/   typed one-argument setters, writable by clients
    Methods/      zero-argument, no-result commands
```

Function annotations map `bool`, `int`, `float`, `str`, `bytes`, and homogeneous `typing.List` values to OPC UA types. The package validates every interface
before allocating an asyncua server, adapts method callbacks, intercepts parameter writes, publishes changed status values, and owns polling shutdown. It does
not know about robots, nested application schemas, or process signals.

### universal-robots-clients

The root package re-exports nothing. Consumers retain protocol context in every call:

```python
import universal_robots_clients.dashboard as dashboard
import universal_robots_clients.program_discovery as program_discovery
```

`dashboard` owns TCP framing, validation, and named Dashboard operations. `program_discovery` owns local and caller-owned SFTP traversal plus an optional
Paramiko connection convenience function. The modules do not import one another. A real `rtde` module will be added only after its dependency, connection
lifecycle, and register contract are proven.

## Gateway dependencies

```text
_01_main
    +-- _02_parse_command_line_args
    +-- _03_compose_gateway

_03_compose_gateway
    +-- _02_parse_command_line_args
    +-- _04_discover_ur_programs
    +-- _05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde
    +-- _06_combine_program_discovery_and_control
    +-- _07_expose_program_commands_via_opcua

_04_discover_ur_programs
    +-- _02_parse_command_line_args
    +-- universal_robots_clients.program_discovery

_05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde
    +-- _02_parse_command_line_args
    +-- universal_robots_clients.dashboard

_06_combine_program_discovery_and_control
    +-- Python standard library only

_07_expose_program_commands_via_opcua
    +-- _06_combine_program_discovery_and_control
    +-- declarative_opcua_server
```

The graph is acyclic. The extracted packages accept ordinary values and callables rather than importing the gateway's `Args` or interface dataclass.

## Runtime flow

```text
_01_main.main()
    -> _02_parse_command_line_args.parse_args()
    -> _03_compose_gateway.compose_gateway()
        -> partial(_04_discover_ur_programs.discover_programs, args)
        -> _05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde.create_dashboard_commands(args)
        -> _06_combine_program_discovery_and_control.create_interfaces(...)
        -> _07_expose_program_commands_via_opcua.create_server(...)
            -> declarative_opcua_server.create_server(...)
    -> _01_main._run_until_stopped(server)
```

Discovery runs during composition. Module 6 uses a comprehension to create a flat `StartProgram_...` method for each program, then adds `PauseProgram` and
`StopProgram`. `ProgramState` currently uses the reusable Dashboard getter; the declarative server polls it and publishes changes. The parameter interface is
empty until RTDE is implemented.

The main module enters the managed server context and waits for `SIGINT` or `SIGTERM`. The declarative package starts its asyncua server and polling thread on
entry and stops both on exit.

## Public gateway APIs

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

_05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde
    DashboardCommand
    DashboardCommands
    create_dashboard_commands

_06_combine_program_discovery_and_control
    GatewayInterfaces
    create_interfaces

_07_expose_program_commands_via_opcua
    OPC_NAMESPACE
    create_server
```

`Args` and `GatewayInterfaces` are frozen data classes. The declarative package uses private dataclasses for managed lifecycle and polling records. Public
functions document their consumers, and cross-module calls retain module namespaces.

## Repository layout

```text
code/
    Dockerfile
    pyproject.toml
    src/ur_dashboard_to_opcua_gateway/
packages/
    declarative_opcua_server/
        pyproject.toml
        README.md
        src/declarative_opcua_server/
        tests/
    universal_robots_clients/
        pyproject.toml
        README.md
        src/universal_robots_clients/
        tests/
docs/
tests/
    architecture/
    unit/
    system/
    support/
```

Package-local tests move with reusable behavior. Gateway tests retain application policy and the Docker-backed compatibility contract across all three
distributions.

## Python compatibility

All distributions support Python 3.8.3 and later. Runtime annotations use Python 3.8-compatible `typing` forms. `declarative-opcua-server` selects asyncua 1.1.5
for Python below 3.10 and asyncua 2.0.1 for newer interpreters. CI runs non-container tests on Python 3.8.3 and 3.12 and runs the real container pipeline on
Python 3.12.
