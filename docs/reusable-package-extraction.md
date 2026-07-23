# Reusable Package Extraction

## Status

The reusable package split is implemented in two public repositories:

1. [`declarative-opcua-server`](https://github.com/CraigBuilds/declarative-opcua-server), imported as `declarative_opcua_server`.
1. [`universal-robots-clients`](https://github.com/CraigBuilds/universal-robots-clients), imported as `universal_robots_clients`.

Each project has its own metadata, README, `src` layout, focused tests, CI, and release workflow. The gateway declares them as dependencies and imports only
their documented package APIs.

The gateway will install their released versions from PyPI; the system suite remains the cross-repository compatibility contract.

## Why these boundaries

The gateway combines three reusable technical capabilities with product-specific policy:

| Capability                          | Owner                                                 | Status              |
| ----------------------------------- | ----------------------------------------------------- | ------------------- |
| Declarative OPC UA exposure         | `declarative_opcua_server`                            | External repository |
| Dashboard protocol operations       | `universal_robots_clients.dashboard_client`           | External repository |
| Discovery backend selection         | `universal_robots_clients.urp_discovery_client`       | External repository |
| Local URP discovery                 | `universal_robots_clients.urp_discovery_local_client` | External repository |
| SFTP URP discovery                  | `universal_robots_clients.urp_discovery_sftp_client`  | External repository |
| RTDE status, control, and registers | `universal_robots_clients.rtde_client`                | Implemented         |
| Program invocation and task policy  | Gateway application                                   | Planned             |

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
- A method function exposes its required annotated arguments as OPC UA inputs and its annotated return as an optional output. Defaulted arguments are treated as
  bound application configuration rather than client inputs.

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
- A plain, unstarted `asyncua.sync.Server` with status polling tied to asyncua's thread-loop lifetime.
- Opinionated loopback, namespace, root, anonymous, and `NoSecurity` defaults.

It does not own:

- Universal Robots or any robot protocol.
- Nested address-space schemas or arbitrary OPC UA node classes.
- Task manifests, invocation IDs, register mappings, or workflow state.
- Process signals, command-line parsing, or application logging policy.
- Certificates and authenticated security policies in the current package.

Applications requiring arbitrary address spaces should use asyncua directly. This package is intentionally not a competing general OPC UA framework.

### Current verification

Package tests use a real asyncua client to browse all three folders, observe polled scalar and list status values, write a parameter, invoke a method, and stop
cleanly. They also verify partial signatures, invalid signatures, and rejection of nested interfaces. The same tests pass on Python 3.8.3 against the compatible
asyncua 1.x line and Python 3.12 against the compatible asyncua 2.x line.

Publication hardening now includes package builds, metadata checks, and clean-environment installation. Further reliability releases should add focused tests
for getter failures, setter failures and client status codes, duplicate or invalid names, port binding failures, and status subscription notifications.

## universal-robots-clients

### Package shape

Consumers import capability modules explicitly:

```python
import universal_robots_clients.dashboard_client as dashboard_client
import universal_robots_clients.rtde_client as rtde_client
import universal_robots_clients.urp_discovery_client as urp_discovery_client
import universal_robots_clients.urp_discovery_local_client as urp_discovery_local_client
import universal_robots_clients.urp_discovery_sftp_client as urp_discovery_sftp_client
```

The root package re-exports nothing. Calls therefore retain ownership context such as `dashboard_client.play_program()` and
`urp_discovery_local_client.discover_programs()`.

### Dashboard client

The public API is:

```text
send_command
load_program
play_program
load_and_play_program
pause_program
stop_program
get_program_state
```

Functions accept direct host, port, timeout, and operation values. Each command validates line framing, opens one connection, verifies the greeting, sends one
command, reads one response, and closes the connection. Raw response strings remain deliberate until command-specific success and failure semantics are
designed. `load_and_play_program()` is the reusable sequential convenience operation used by generated gateway methods; it deliberately does not interpret the
load response yet.

The module knows nothing about `Args`, discovery, RTDE, OPC UA, program method naming, or process lifecycle.

### URP discovery clients

The selector client exposes:

```text
discover_programs
```

`urp_discovery_local_client.discover_programs()` performs local traversal. `urp_discovery_sftp_client.discover_programs()` accepts a caller-owned connected SFTP
client, while `connect_and_discover_programs()` owns a short Paramiko connection. All paths find case-insensitive `.urp` files recursively, normalize relative
paths, and sort results. Paramiko belongs to the optional `sftp` extra and is imported only by the managed SFTP connection operation.

The gateway remains responsible for environment-variable passwords, prompts, and its current decision to trust unknown keys.

### RTDE client

The implemented `universal_robots_clients.rtde_client` module loads the optional `ur-rtde` dependency only when connecting. Its public functional API is:

```text
Client
connect
disconnect
is_connected
reconnect
read_actual_tcp_pose
read_actual_tcp_speed
read_actual_tcp_force
read_actual_joint_positions
read_joint_temperatures
read_robot_mode
read_safety_mode
read_runtime_state
is_protective_stopped
is_emergency_stopped
read_speed_slider_fraction
read_speed_scaling
write_speed_slider_fraction
read_tool_digital_input
read_tool_digital_output
write_tool_digital_output
read_output_int_register
read_output_double_register
write_input_int_register
write_input_double_register
```

`Client` is a frozen data class that owns the two persistent `ur-rtde` interfaces and a lock; all behavior remains in module functions. The default upper
register range is intended for external RTDE clients, with lower registers available explicitly. Unit tests cover configuration, lifecycle, reconnection,
telemetry, speed, tool I/O, ranges, and typed reads/writes, while the system suite verifies the contract against URSim.

The package owns protocol mechanics plus reusable adapter conveniences: a configured lazy RTDE endpoint, human-facing speed percentages, and configured
program catalogues with deterministic method generation. The gateway continues to own OPC UA names, task schemas, register allocation, commit and
acknowledgement rules, invocation serialization, and
execution strategy. Basic speed and gripper controls are implemented; atomic task invocation is not.

## Remaining gateway policy

The application still owns meaningful behavior:

- Parse all product configuration into `Args`.
- Configure local or SFTP discovery through the package's selector.
- Bind robot endpoints to reusable functions.
- Add generic list, load, run, pause, and stop methods.
- Select which getter is published as `ProgramState`.
- Choose OPC UA names for RTDE telemetry and label tool I/O as generic gripper signals.
- Supply the `UR20` root, namespace, and endpoint.
- Own process signals and the complete system test.

Program-path normalization, speed conversion, configured lazy RTDE lifetime, and live method-refresh mechanics now live in the reusable packages. The remaining
policy is expressed directly in `gateway.py` as configured callables passed to `create_server()`.

## Local development and release path

Install the gateway and let pip resolve the released reusable packages from PyPI:

```bash
python -m pip install -e "./code[sftp,system-test]"
```

Release preparation completed in the package repositories includes:

- Package-focused READMEs, examples, detailed module docstrings, changelogs, typed-package markers, bounded dependencies, and PyPI metadata.
- Source-distribution and wheel builds, `twine check`, and clean wheel installation on Python 3.8.3 and Python 3.12 with all optional dependencies.
- The complete non-container suites on Python 3.8.3 and Python 3.12 plus the Dashboard, SFTP, OPC UA, and RTDE URSim pipeline.
- CI jobs that repeat build, metadata, clean-install, import, and package-owned test checks for every change.
- Real Dashboard and RTDE tests against official URSim plus local-filesystem and real OpenSSH/SFTP discovery tests in `universal-robots-clients`.

The initial reusable-package release completed with:

1. Version 0.3.0 artifacts published through PyPI trusted publishing with matching Git tags.
1. Normal package-index resolution in gateway development, CI, Docker, and system-test environments.
1. The gateway system suite retained as the compatibility contract between released versions; failure-focused tests remain required before promotion beyond
   alpha.

Independent publication introduces versioning, changelog, CI, security, and compatibility costs. Those costs are justified only if each package remains useful
without the gateway, which the current boundaries now demonstrate.
