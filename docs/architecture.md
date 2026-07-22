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
            +-- ur-rtde [optional RTDE extra]
```

The two package projects do not depend on one another. The gateway is a deliberately small product-specific composition layer that combines their public
functions, owns its configuration, and runs the resulting server.

## Gateway reading order

```text
main.py
    Parse configuration, compose the gateway, and own process startup and shutdown.

args.py
    Resolve command-line, environment, default, and validation rules into Args.

gateway.py
    Select discovery, connect RTDE, bind robot operations, build flat interfaces, and compose resource lifetimes.
```

There are no application adapter modules between the composition root and the reusable packages: the package APIs are already narrow enough to call directly.

## Package responsibilities

### declarative-opcua-server

The package exposes `declarative_opcua_server.create_server()` and `update_method_interface()`. Server creation receives three flat mappings:

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
    Methods/      typed functions exposed as OPC UA methods
```

Function annotations map `bool`, `int`, `float`, `str`, `bytes`, and homogeneous `typing.List` values to OPC UA types. Required annotated method arguments
become OPC UA inputs, and an annotated return becomes an output. The package validates every interface before allocating and returning a plain
`asyncua.sync.Server`, adapts method callbacks, intercepts parameter writes, and publishes changed status values. A complete replacement method mapping can add,
remove, or replace live method nodes while preserving unchanged callables and NodeIds. The package does not know about robots, application schemas, or process
signals.

### universal-robots-clients

The root package re-exports nothing. Consumers retain protocol context in every call:

```python
import universal_robots_clients.dashboard_client as dashboard_client
import universal_robots_clients.rtde_client as rtde_client
import universal_robots_clients.urp_discovery_client as urp_discovery_client
```

`dashboard_client` owns TCP framing, validation, and named Dashboard operations. `urp_discovery_client` selects the explicit local and SFTP discovery clients;
only `urp_discovery_sftp_client` can load optional Paramiko. `rtde_client` owns the `ur-rtde` receive and I/O connections, common telemetry, tool digital I/O,
speed-slider control, and typed integer/double register I/O. Invocation schemas, register allocation, and commit/acknowledgement policy remain gateway concerns.

## Dependencies

```text
main
    +-- args
    +-- gateway

args
    +-- Python standard library only

gateway
    +-- args
    +-- declarative_opcua_server
    +-- universal_robots_clients.dashboard_client
    +-- universal_robots_clients.rtde_client
    +-- universal_robots_clients.urp_discovery_client
```

The graph is acyclic. The extracted packages accept ordinary values and callables and never import the gateway's `Args`. Cross-module calls retain module
namespaces so their owner remains visible at each call site.

## Runtime flow

```text
main.main()
    -> args.parse_args()
    -> gateway.compose_gateway(args)
        -> universal_robots_clients.urp_discovery_client.discover_programs(...)
        -> universal_robots_clients.rtde_client.connect(...)
        -> build Dashboard methods plus RTDE status and parameter callables
        -> declarative_opcua_server.create_server(...)
        -> wrap the server and RTDE client in one gateway lifetime
    -> main._run_until_stopped(gateway)
```

Discovery runs during composition to generate a flat `StartProgram_...` method for each program. `RefreshPrograms` repeats discovery and passes the complete
desired mapping to `declarative_opcua_server.update_method_interface()`, which changes the live `Methods` folder without restarting the server. Unchanged
programs preserve their callbacks and nodes. The root also exposes dynamic `ListPrograms`, `LoadProgram(program)`, `RunProgram`, `PauseProgram`, and
`StopProgram` methods. A generated start method binds the reusable Dashboard `load_and_play_program()` operation, while the generic methods let a client perform
those steps separately. `ProgramState` uses the reusable Dashboard getter. The remaining status callbacks read RTDE telemetry, and parameter callbacks set the
speed slider or tool outputs. The declarative server infers OPC UA types from those functions' annotations, polls status, and validates writes.

The main module enters the composed gateway context and waits for `SIGINT` or `SIGTERM`. The wrapper starts/stops asyncua first and disconnects RTDE last, which
prevents the status thread from polling a closed RTDE client. A failed server construction or startup also closes RTDE.

## Public gateway API

```text
main
    main

args
    Args
    parse_args

gateway
    OPC_NAMESPACE
    compose_gateway
```

`Args` is the public configuration data class. The private `_Gateway` data class only couples resource lifetimes. Other helpers begin with an underscore because
they implement composition details rather than APIs for other modules.

## Repository layout

```text
code/
    Dockerfile
    pyproject.toml
    src/ur_dashboard_to_opcua_gateway/
docs/
tests/
    architecture/
    unit/
    system/
    support/
```

Package-local tests live in the two standalone package repositories. Gateway tests retain application policy and the Docker-backed compatibility contract across
all three distributions.

## Python compatibility

All distributions support Python 3.8.3 and later. Runtime annotations use Python 3.8-compatible `typing` forms. `declarative-opcua-server` selects the asyncua
1.x line from 1.1.5 for Python below 3.10 and the 2.x line from 2.0.1 for newer interpreters. CI runs non-container tests on Python 3.8.3 and 3.12 and runs the
real container pipeline on Python 3.12.
