# Reusable Package Extraction

## Status

The first local extraction is implemented. Two independent distribution projects now live beneath `packages/`:

1. `declarative-opcua-server`, imported as `declarative_opcua_server`.
1. `universal-robots-clients`, imported as `universal_robots_clients`.

Each project has its own metadata, README, `src` layout, and focused tests. The gateway declares them as dependencies and imports only their documented package
APIs. CI and the Docker image install them as separate distributions before installing the gateway.

They remain in this repository while their APIs are proven. “Extracted” currently means architecturally and distributably separate, not yet published to a
package index or moved to external repositories.

## Why these boundaries

The gateway combines three reusable technical capabilities with product-specific policy:

| Capability                         | Owner                                        | Status                    |
| ---------------------------------- | -------------------------------------------- | ------------------------- |
| Declarative OPC UA exposure        | `declarative_opcua_server`                   | Implemented locally       |
| Dashboard protocol operations      | `universal_robots_clients.dashboard`         | Implemented locally       |
| Local and SFTP URP discovery       | `universal_robots_clients.program_discovery` | Implemented locally       |
| RTDE connection and register I/O   | `universal_robots_clients.rtde`              | Planned after prototyping |
| Program invocation and task policy | Gateway application                          | Planned                   |

The two distributions do not depend on one another. The Universal Robots modules also do not import one another. Only the gateway knows that discovered programs
become Dashboard-backed OPC UA methods.

## declarative-opcua-server

### Public API

The package deliberately exposes one function:

```python
import declarative_opcua_server

server = declarative_opcua_server.create_server(
    status_interface={
        "ToolVoltage": read_tool_voltage,
        "ProgramRunning": read_program_running,
    },
    parameter_interface={
        "TriangleRoutineHeight": write_triangle_routine_height,
    },
    method_interface={
        "StartTriangleRoutine": start_triangle_routine,
    },
    endpoint="opc.tcp://127.0.0.1:4840/",
    namespace="urn:example:robot",
    root_object="Robot",
)

with server:
    wait_for_shutdown()
```

All interfaces are flat. The package creates exactly three folders beneath the root:

```text
Robot/
    Status/
    Parameters/
    Methods/
```

The selected interface defines a function's role:

- A status function accepts no arguments and declares a supported return type. The package polls it and publishes changed values through a read-only variable.
- A parameter function accepts one annotated argument and returns no value. An OPC UA client write invokes it before the value is retained.
- A method function accepts no arguments and returns no value. An OPC UA method call invokes it.

There is no generic `data_interface`, descriptor hierarchy, `Folder`, `Object`, `Method`, `Variable`, `set_output()`, or caller-managed node handle API.

### Supported values

The internal type map is fixed rather than caller-configurable:

| Python annotation | OPC UA variant type |
| ----------------- | ------------------- |
| `bool`            | `Boolean`           |
| `int`             | `Int64`             |
| `float`           | `Double`            |
| `str`             | `String`            |
| `bytes`           | `ByteString`        |
| `typing.List[T]`  | One-dimensional `T` |

`T` must be one of the supported scalar annotations. Python `float` maps to OPC UA `Double`, matching Python precision and UR RTDE double values. Missing,
unsupported, nested, or contextually invalid definitions fail before asyncua resources are allocated. Configured `functools.partial` functions are supported
because the gateway relies on them heavily.

### Responsibilities

The package owns:

- Synchronous asyncua server configuration.
- The fixed root, `Status`, `Parameters`, and `Methods` structure.
- Strict flat-interface and signature validation.
- Python-to-OPC-UA type mapping.
- Method callback adaptation.
- Status polling and subscription-visible updates.
- Parameter write interception.
- Managed startup and shutdown of asyncua and polling resources.
- Opinionated loopback, namespace, root, anonymous, and `NoSecurity` defaults.

It does not own:

- Universal Robots or any robot protocol.
- Nested address-space schemas or arbitrary OPC UA node classes.
- Task manifests, invocation IDs, register mappings, or workflow state.
- Process signals, command-line parsing, or application logging policy.
- Certificates and authenticated security policies in version 0.1.

Applications requiring arbitrary address spaces should use asyncua directly. This package is intentionally not a competing general OPC UA framework.

### Current verification

Package tests use a real asyncua client to browse all three folders, observe polled scalar and list status values, write a parameter, invoke a method, and stop
cleanly. They also verify partial signatures, invalid signatures, and rejection of nested interfaces. The same tests pass on Python 3.8.3 with asyncua 1.1.5 and
Python 3.12 with asyncua 2.0.1.

Before external publication, add focused tests for getter failures, setter failures and client status codes, duplicate or invalid names, port binding failures,
status subscription notifications, package builds, and installation into a clean environment.

## universal-robots-clients

### Package shape

Consumers import capability modules explicitly:

```python
import universal_robots_clients.dashboard as dashboard
import universal_robots_clients.program_discovery as program_discovery
```

The root package re-exports nothing. Calls therefore retain ownership context such as `dashboard.play_program()` and
`program_discovery.discover_local_programs()`.

### Dashboard module

The public API is:

```text
send_command
load_program
play_program
pause_program
stop_program
get_program_state
```

Functions accept direct host, port, timeout, and operation values. Each command validates line framing, opens one connection, verifies the greeting, sends one
command, reads one response, and closes the connection. Raw response strings remain deliberate until command-specific success and failure semantics are
designed.

The module knows nothing about `Args`, discovery, RTDE, OPC UA, program method naming, load-plus-play policy, or process lifecycle.

### Program-discovery module

The public API is:

```text
discover_local_programs
discover_sftp_programs
discover_programs_over_sftp
```

Both traversal paths find case-insensitive `.urp` files recursively, normalize relative paths, and sort results. The lowest-level SFTP function accepts a
caller-owned connected client. The convenience function owns a short Paramiko connection and requires unknown-host-key trust to be selected explicitly. Paramiko
belongs to the optional `sftp` extra and is imported only by that convenience function.

The gateway remains responsible for environment-variable passwords, prompts, backend selection, and its current decision to trust unknown keys.

### RTDE module

There is no placeholder RTDE implementation. A future `universal_robots_clients.rtde` module should be added only after selecting a maintained RTDE dependency
and proving these contracts against URSim:

- Connection negotiation, recipe setup, and shutdown.
- Persistent receive lifecycle and thread-safety.
- Typed status getters suitable for `status_interface`.
- Typed register setters suitable for `parameter_interface`.
- Timeouts, disconnection, reconnect, and controller compatibility.

The package will own protocol mechanics. The gateway will continue to own task schemas, register allocation, commit and acknowledgement rules, invocation
serialization, and execution strategy.

## Remaining gateway policy

The application still owns meaningful behavior:

- Parse all product configuration into `Args`.
- Select local or SFTP discovery.
- Bind robot endpoints to reusable functions.
- Discover programs during composition.
- Generate deterministic flat `StartProgram_...` names.
- Define load-then-play invocation behavior.
- Add controller-wide pause and stop methods.
- Select which getter is published as `ProgramState`.
- Supply the `UR20` root, namespace, and endpoint.
- Own process signals and the complete system test.

RTDE will add product-specific task schemas, parameter mappings, and resource composition rather than moving those decisions into either reusable package.

## Local development and release path

The monorepo currently installs the package projects first:

```bash
python -m pip install -e ./packages/declarative_opcua_server
python -m pip install -e "./packages/universal_robots_clients[sftp]"
python -m pip install -e "./code[sftp]"
```

The next extraction steps are:

1. Complete each version 0.1 failure and build contract.
1. Build wheels and source distributions and install them in clean test environments.
1. Run the gateway's Python 3.8, Python 3.12, and URSim suites against those artifacts.
1. Check distribution and repository names immediately before publication.
1. Move each package project to its own repository without changing import paths.
1. Publish bounded releases and replace local development installation with package-index resolution.
1. Keep the gateway system suite as the compatibility contract between released versions.

Independent publication introduces versioning, changelog, CI, security, and compatibility costs. Those costs are justified only if each package remains useful
without the gateway, which the current boundaries now demonstrate.
