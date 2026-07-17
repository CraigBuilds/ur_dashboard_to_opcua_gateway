# Architecture

## Overview

The repository contains three independently installable Python distributions:

```text
ur_dashboard_to_opcua_gateway
    +-- declarative-opcua-server
    |       +-- asyncua
    +-- universal-robots-clients
            +-- Python standard library
            +-- paramiko [optional SFTP extra]
```

The two package projects do not depend on one another. The gateway is a deliberately small product-specific composition layer that combines their public
functions, owns its configuration, and runs the resulting server.

## Gateway reading order

```text
_01_main.py
    Parse configuration, compose the gateway, and own process startup and shutdown.

_02_parse_command_line_args.py
    Resolve command-line, environment, default, and validation rules into Args.

_03_compose_gateway.py
    Select discovery, bind Dashboard operations, build flat interfaces, and create the server.
```

The numeric prefixes keep the complete application reading order visible in an alphabetical listing. There are no application adapter modules between the
composition root and the reusable packages: the package APIs are already narrow enough to call directly.

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
not know about robots, application schemas, or process signals.

### universal-robots-clients

The root package re-exports nothing. Consumers retain protocol context in every call:

```python
import universal_robots_clients.dashboard as dashboard
import universal_robots_clients.program_discovery as program_discovery
```

`dashboard` owns TCP framing, validation, and named Dashboard operations. `program_discovery` owns local and caller-owned SFTP traversal plus an optional
Paramiko connection convenience function. The modules do not import one another. A real `rtde` module will be added only after its dependency, connection
lifecycle, and register contract are proven.

## Dependencies

```text
_01_main
    +-- _02_parse_command_line_args
    +-- _03_compose_gateway

_02_parse_command_line_args
    +-- Python standard library only

_03_compose_gateway
    +-- _02_parse_command_line_args
    +-- declarative_opcua_server
    +-- universal_robots_clients.dashboard
    +-- universal_robots_clients.program_discovery
```

The graph is acyclic. The extracted packages accept ordinary values and callables and never import the gateway's `Args`. Cross-module calls retain module
namespaces so their owner remains visible at each call site.

## Runtime flow

```text
_01_main.main()
    -> _02_parse_command_line_args.parse_args()
    -> _03_compose_gateway.compose_gateway(args)
        -> universal_robots_clients.program_discovery.*
        -> build StartProgram_..., PauseProgram, StopProgram, and ProgramState callables
        -> declarative_opcua_server.create_server(...)
    -> _01_main._run_until_stopped(server)
```

Discovery runs once during composition. The composition root uses a comprehension to create a flat `StartProgram_...` method for each program and adds
controller-wide pause and stop methods. A start method applies the gateway's load-then-play policy through qualified Dashboard package calls. `ProgramState`
uses the reusable Dashboard getter; the declarative server polls it and publishes changes. The parameter interface remains empty until RTDE is implemented.

The main module enters the managed server context and waits for `SIGINT` or `SIGTERM`. The declarative package starts its asyncua server and polling thread on
entry and stops both on exit.

## Public gateway API

```text
_01_main
    main

_02_parse_command_line_args
    Args
    parse_args

_03_compose_gateway
    OPC_NAMESPACE
    compose_gateway
```

`Args` is the application's only data class. All other gateway helpers begin with an underscore because they implement composition details rather than APIs for
other modules. Public functions document their consumers.

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
