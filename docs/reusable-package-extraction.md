# Reusable Package Extraction

## Purpose

This report proposes extracting two reusable Python distributions from the gateway:

1. A generic OPC UA method server that exposes Python callables from a declarative method tree.
1. A Universal Robots client library containing separate modules for Dashboard control, RTDE communication, and UR program-file discovery.

The remaining `ur_dashboard_to_opcua_gateway` application would install those distributions, apply gateway-specific policy, compose their APIs, and own process
configuration and lifecycle. This direction preserves the current functional architecture while making the generic OPC UA adapter and the collection of
robot-facing Universal Robots integrations independently reusable.

This is a proposed target architecture. The distributions have not yet been extracted.

The later [multi-protocol gateway architecture](multi-protocol-gateway-architecture.md) extends this proposal for parameterized program invocation. Dashboard
control and program discovery are already stable enough to extract. RTDE should remain inside the gateway until its public contract is proven, then move into
the same Universal Robots client distribution rather than becoming another independently versioned package. The OPC UA package scope should be finalized only
after writable argument variables, invocation state, and events are proven.

## Summary

The current and planned capabilities suggest these package boundaries:

| Current or planned capability                                                                     | Proposed module                              | Suitability                                                        |
| ------------------------------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------ |
| Dashboard behavior in `_05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde`    | `universal_robots_clients.dashboard`         | Strongest and most immediately reusable candidate                  |
| Planned RTDE behavior in `_05_control_ur_programs_and_exchange_parameters_via_dashboard_and_rtde` | `universal_robots_clients.rtde`              | Strong after its narrow public contract is proven in the gateway   |
| `_04_discover_ur_programs`                                                                        | `universal_robots_clients.program_discovery` | Strong, after configuration and SSH policy are decoupled           |
| `_07_expose_program_commands_via_opcua`                                                           | `opcua_method_server`                        | Strong if its address-space model remains deliberately constrained |

The other production modules should remain application code:

- `_01_main` owns this process's entry point and lifecycle.
- `_02_parse_command_line_args` defines this application's combined configuration.
- `_03_compose_gateway` is this application's composition root.
- `_06_combine_program_discovery_and_control` defines gateway-specific command and per-program operation policy.

The extraction should reduce the gateway rather than merely move its existing coupling into other repositories. Each distribution must accept ordinary values
and callables instead of depending on the gateway's `Args`, command registry, module names, OPC UA object names, or process lifecycle.

Dashboard, RTDE, and program discovery belong in one distribution because they are all reusable ways of interacting with a Universal Robots controller or its
program assets and are likely to be installed by the same applications. They should remain separate import modules because their protocols, optional
dependencies, connection lifecycles, and failure modes are different. Cohesion at the distribution level must not become coupling at the implementation level.

## Design principles

Each proposed distribution should:

- Have one coherent responsibility and a small public API.
- Be useful without installing or importing the gateway.
- Accept ordinary Python values, callables, protocols, or standard-library types.
- Avoid embedding gateway-specific defaults such as `UR20`, `ProgramShortcuts`, or the gateway OPC UA namespace.
- Keep transport policy explicit, especially network binding, authentication, host verification, and timeouts.
- Support Python 3.8.3 for as long as the gateway supports it, or publish a compatible version range that the gateway can pin.
- Carry its own focused unit tests and documentation.
- Remain functional unless state and resource ownership provide a concrete benefit.
- Add features only when a real consumer needs them.

Within `universal_robots_clients`, the `dashboard`, `program_discovery`, and `rtde` modules should not import one another. A small shared module is justified
only for conventions that genuinely repeat, such as endpoint data or common connection errors. The package should not introduce one stateful client that opens
and owns all three protocols because their connection and resource lifecycles are materially different.

The gateway should retain end-to-end tests across the installed distributions. Passing each distribution's unit tests is necessary but does not prove that their
released versions compose correctly.

## Generic OPC UA method server

### Goal

The OPC UA package would create a synchronous server from a nested mapping of names to Python callables. A consumer should be able to provide functions and
receive an OPC UA address space whose methods reflect those functions' signatures and return annotations.

`opcua_method_server` is the clearest working name because it is searchable and states both the protocol and purpose. `QuickMethodServer` communicates
convenience but does not identify OPC UA without additional context. Other reasonable names are `opcua_function_server` and `simple_opcua_method_server`.

### Proposed API

An initial API could look like:

```python
import opcua_method_server

methods = {
    "programs": discover_programs,
    "load": load_program,
    "start": start_program,
    "ProgramShortcuts": {
        "Main.urp": {
            "load": load_main,
            "run": run_main,
        },
    },
}

server = opcua_method_server.create_server(
    methods,
    endpoint="opc.tcp://127.0.0.1:4840/",
    namespace="urn:example:program-control",
    root_object="Robot",
)
```

For the first version, the mapping can use two rules:

- A callable value becomes an OPC UA method.
- A mapping value becomes a nested OPC UA object or folder containing more methods.

The package must define whether nested mappings create folders or objects. If consumers need both node classes, a later version can add explicit lightweight
descriptors such as `Folder(...)` and `Object(...)`. The first release should not build a general-purpose OPC UA schema framework.

### Package responsibilities

The package should own:

- Synchronous `asyncua` server creation.
- Endpoint and namespace registration.
- Creation of a configured root object.
- Recursive conversion of a method tree into OPC UA nodes.
- Function-signature inspection.
- OPC UA input and output argument metadata.
- Adaptation of Python callables to OPC UA method callbacks.
- A documented set of supported Python argument and return types.
- Safe local defaults and clear configuration overrides.

The first supported type set can remain close to proven gateway requirements:

- `str`
- `typing.List[str]`
- Functions with zero or more string inputs
- Synchronous functions

Additional scalar types, structured values, asynchronous functions, custom status codes, and richer schemas should be added only with tests and concrete use
cases.

### Package exclusions

The package should not know about:

- Universal Robots.
- Program discovery.
- Dashboard commands.
- `UR20` or `ProgramShortcuts`.
- The gateway's `CommandRegistry`.
- Signal handling or process lifetime.
- Gateway command-line arguments.

### Defaults and security

A convenience server that defaults to OPC UA `NoSecurity` should bind to loopback by default. Listening on `0.0.0.0` must require an explicit endpoint. The API
and documentation should make the security state visible rather than silently presenting an insecure externally reachable service as a production default.

Certificates, authentication, secure policies, custom application URIs, and failure-to-status mapping can be later package features. The gateway can initially
continue to request the behavior it currently uses.

### Main design risk

The primary risk is overgeneralization. `asyncua` already supplies the complete OPC UA implementation; this package should remain a concise adapter from
callables to a useful method-oriented address space, not become a competing OPC UA framework.

## Universal Robots clients

### Goal and name

This distribution would collect reusable Python integrations for Universal Robots controllers and program assets. It would be useful to commissioning scripts,
diagnostics, automated tests, manufacturing tools, alternative gateways, and applications that do not use OPC UA.

The recommended distribution name is `universal-robots-clients`, with the import package `universal_robots_clients`. This is more explicit and searchable than
`ur-clients`, which depends on readers already knowing what "UR" means and can be mistaken for a generic client collection. `ur-robot-clients` is a reasonable
shorter alternative, but the full vendor name provides better context. Package availability must be checked again immediately before publication, and the
project metadata should state clearly that this is an independent library rather than an official Universal Robots product.

The distribution should expose separate `dashboard`, `program_discovery`, and `rtde` modules. Users should import the module that owns the operation being
called:

```python
import universal_robots_clients.dashboard as dashboard
import universal_robots_clients.program_discovery as program_discovery
import universal_robots_clients.rtde as rtde
```

The root package should not re-export every function. Keeping calls qualified as `dashboard.play_program()`, `program_discovery.discover_local_programs()`, and
`rtde.<operation>()` makes protocol ownership visible and avoids name collisions as the package grows.

### Dashboard client

#### Goal

The `dashboard` module would provide ordinary Python functions for communicating with a Universal Robots Dashboard Server.

#### Proposed API

The public API should use direct connection values rather than the gateway's `Args`:

```python
import universal_robots_clients.dashboard as dashboard

state = dashboard.get_program_state("192.0.2.10")
loaded = dashboard.load_program("192.0.2.10", "Production/PickPart.urp")
started = dashboard.play_program("192.0.2.10")
dashboard.pause_program("192.0.2.10")
dashboard.stop_program("192.0.2.10")
```

The low-level operation should also remain available:

```python
response = dashboard.send_command(
    host="192.0.2.10",
    command="robotmode",
    port=29999,
    timeout=5.0,
)
```

An optional immutable endpoint dataclass may be worthwhile when callers repeatedly use the same host, port, and timeout. It should be a convenience layer, not a
requirement for simple function calls.

#### Responsibilities

The `dashboard` module should own:

- Dashboard TCP connection and line framing.
- Greeting and response handling.
- Command injection validation.
- Default Dashboard port and timeout.
- Public functions for supported Dashboard operations.
- Clearly documented transport exceptions.
- Tests for protocol framing, incomplete responses, timeouts, and command construction.

The first release can preserve raw string responses to keep the extraction behaviorally small. Typed response interpretation should be designed later because
different Dashboard commands use different textual success and failure conventions.

#### Exclusions

The `dashboard` module should not know about:

- SFTP or local program discovery.
- RTDE recipes or register exchange.
- OPC UA.
- Gateway command names such as `start` when the Dashboard command is `play`.
- The gateway's `Args`.
- Per-program operations.
- Gateway-wide concurrency or load-and-start policy.

The gateway can adapt `play_program()` to its public `start` command and decide how to compose `load` followed by `play`.

#### Future features

Likely future additions include:

- More Dashboard commands.
- Typed or classified responses.
- Explicit connection and protocol exception types.
- Persistent connections or sessions.
- Reconnection and stale-session handling.
- Optional command serialization.

Persistent connections should not be part of the initial extraction. The current connection-per-command behavior is simple, stateless, and already tested.

### Program discovery

#### Goal

The `program_discovery` module would find `.urp` files from local filesystems and remote SFTP trees and return deterministic paths relative to a configured
program root. It could support program browsers, deployment checks, backup tools, auditing, synchronization, and gateways using protocols other than OPC UA.

Local traversal is not a network client in the narrow sense, but it accesses the same UR program resource as SFTP and applies the same `.urp` filtering,
relative path normalization, and sorting rules. Keeping both backends in `universal_robots_clients.program_discovery` gives callers one discovery contract
regardless of whether the robot's program directory is mounted locally or reached through SFTP.

#### Proposed API

Local discovery should require only a path:

```python
import universal_robots_clients.program_discovery as program_discovery

catalog = program_discovery.discover_local_programs("/programs")
```

The lowest-level SFTP API should accept an already connected SFTP client:

```python
catalog = program_discovery.discover_sftp_programs(
    sftp_client,
    "/programs",
)
```

This boundary keeps authentication, host-key policy, SSH keys, connection timeouts, and connection ownership outside the discovery algorithm. A separately
documented convenience function may open an SFTP connection for simple callers:

```python
catalog = program_discovery.discover_programs_over_sftp(
    host="192.0.2.10",
    root="/programs",
    username="robot",
    password=password,
)
```

Paramiko should remain an optional package extra if local discovery can operate without it:

```bash
python -m pip install "universal-robots-clients[sftp]"
```

#### Responsibilities

The `program_discovery` module should own:

- Case-insensitive `.urp` identification.
- Recursive local filesystem traversal.
- Recursive SFTP traversal.
- Relative path normalization with forward-slash separators.
- Deterministic sorting.
- Clear errors for invalid roots and unsupported directory entries.

#### Exclusions

The `program_discovery` module should not know about:

- The gateway's `Args`.
- Dashboard control.
- RTDE communication.
- OPC UA.
- Password prompting or environment-variable names.
- A mandatory SSH host-key acceptance policy.
- Program execution or per-program operation creation.

The convenience SFTP function may expose host-key policy explicitly, but the core traversal function should work with a caller-owned client and therefore avoid
making that decision.

### RTDE client

#### Goal and timing

The `rtde` module would provide the RTDE operations needed by parameterized program invocation and other robot-data consumers. It belongs in the same
distribution as Dashboard control because both are client protocols for the same controller and will commonly be used together. It should not be a separate
package merely because it uses another TCP port and protocol.

RTDE should first be implemented and proven inside the gateway. Once its useful public contract is clear, that implementation and its focused tests should move
into `universal_robots_clients.rtde`. Adding the module later lets the first package release contain the already understood Dashboard and program-discovery APIs
without prematurely freezing an RTDE abstraction.

#### Intended responsibilities

The `rtde` module may eventually own:

- RTDE connection setup, protocol negotiation, and teardown.
- Recipe configuration for the supported input and output values.
- Reading robot state required by higher-level consumers.
- Writing input registers used by a caller-defined invocation protocol.
- Timeouts, reconnect behavior, and protocol-specific exceptions.
- Focused tests against fakes and URSim.

It should expose protocol capabilities, not gateway task policy. Invocation identifiers, argument schemas, acknowledgement rules, retries, cancellation, and
workflow state remain in the gateway's protocol-neutral coordinator.

The final API should be designed after deciding whether to use the official RTDE Python client, `ur_rtde`, or another maintained implementation. If a
third-party library already provides the required behavior, this module should add only a small, useful facade or compatibility layer; it should not reimplement
RTDE or hide a capable dependency behind a narrower API without a concrete benefit.

### Distribution structure and dependencies

The intended source layout is:

```text
universal_robots_clients/
    __init__.py
    dashboard.py
    program_discovery.py
    rtde.py
```

The base installation should provide Dashboard and local program discovery using the Python standard library. Optional dependencies should remain feature
specific:

```bash
python -m pip install universal-robots-clients
python -m pip install "universal-robots-clients[sftp]"
python -m pip install "universal-robots-clients[rtde]"
python -m pip install "universal-robots-clients[all]"
```

The `sftp` extra would install Paramiko. The `rtde` extra would install whichever RTDE implementation is selected after evaluation. Importing or using an
optional module without its dependency should produce a clear installation error, while Dashboard and local discovery must continue to work without either
extra.

### Distribution exclusions

The Universal Robots client package should not own:

- OPC UA nodes, methods, status codes, or server lifecycle.
- The gateway's `Args`, `CommandRegistry`, public command names, or per-program operation tree.
- Program invocation schemas, cross-protocol coordination, or application workflow state.
- Atomic load-and-start policy or serialization across independent callers.
- Password prompting, environment-variable names, signal handling, or process lifecycle.
- One umbrella `RobotClient` that implicitly opens Dashboard, SFTP, and RTDE resources together.

The package supplies robot-facing capabilities. Applications decide which capabilities to configure, how to compose them, and who owns their lifecycles.

## The remaining gateway application

After extraction, this repository should contain only the policy and wiring that make these libraries into the specific `ur_dashboard_to_opcua_gateway`
application:

- Parse command-line and environment configuration.
- Select local or SFTP discovery.
- Bind Dashboard host, port, and timeout.
- Configure RTDE recipes and connection ownership when parameterized invocation is added.
- Choose gateway command names.
- Create per-program `load` and `run` operations.
- Define the `UR20` root object, `ProgramShortcuts` structure, OPC UA namespace, and endpoint.
- Compose the installed distributions.
- Own signal handling, startup, and shutdown.
- Retain the complete Docker-backed system test.

A possible composition shape is:

```python
import functools

import opcua_method_server
import universal_robots_clients.dashboard as dashboard
import universal_robots_clients.program_discovery as program_discovery

discover_programs = functools.partial(
    program_discovery.discover_local_programs,
    args.programs_folder,
)

dashboard_commands = {
    "load": functools.partial(dashboard.load_program, args.dashboard_host),
    "start": functools.partial(dashboard.play_program, args.dashboard_host),
    "pause": functools.partial(dashboard.pause_program, args.dashboard_host),
    "stop": functools.partial(dashboard.stop_program, args.dashboard_host),
    "status": functools.partial(dashboard.get_program_state, args.dashboard_host),
}

methods = gateway_commands.create_method_tree(discover_programs, dashboard_commands)

server = opcua_method_server.create_server(
    methods,
    endpoint=args.opcua_endpoint,
    namespace="urn:ur20:program-control",
    root_object="UR20",
)
```

SFTP selection, port binding, timeout binding, and per-program operation construction have been omitted from this example for readability. They remain
application composition concerns. A future RTDE adapter would be imported from `universal_robots_clients.rtde`, while invocation schemas and workflow
coordination would remain application code.

The resulting gateway may be only a small amount of production code, but it still has a meaningful responsibility: it defines how the generic OPC UA server and
the required Universal Robots client modules are configured and combined into one deployable product.

## Target dependency graph

```text
ur_dashboard_to_opcua_gateway
    +-- opcua_method_server
    |       +-- asyncua
    |
    +-- universal_robots_clients
            +-- dashboard
            |       +-- Python standard library
            +-- program_discovery
            |       +-- Python standard library
            |       +-- paramiko [optional SFTP extra]
            +-- rtde
                    +-- selected RTDE implementation [optional RTDE extra]
```

The two reusable distributions should not depend on one another. The modules inside `universal_robots_clients` should also remain independent except for a
minimal shared foundation justified by repeated protocol-neutral behavior. The gateway is the only layer that understands their combined use.

## Testing ownership

Tests should move with the behavior they verify:

### `opcua_method_server`

- Signature-to-argument conversion.
- Supported scalar and array return metadata.
- Nested method-tree construction.
- Namespace, endpoint, and root-object configuration.
- Callback adaptation.
- Security defaults.

### `universal_robots_clients.dashboard`

- Command validation.
- Greeting and response exchanges.
- Connection failures and timeouts.
- Exact Dashboard command formatting.
- Public command functions.

### `universal_robots_clients.program_discovery`

- Local traversal.
- SFTP traversal with fake clients.
- `.urp` filtering.
- Relative path normalization.
- Deterministic ordering.
- Optional dependency behavior.

### `universal_robots_clients.rtde`

- Protocol negotiation and recipe configuration.
- Input and output value handling.
- Connection teardown, timeouts, and reconnect behavior.
- Compatibility with supported controller and PolyScope versions.
- Real RTDE exchanges against URSim.

### `ur_dashboard_to_opcua_gateway`

- Command-line parsing.
- Gateway command and per-program operation policy.
- Composition against package APIs.
- Protocol-neutral invocation schemas and coordination.
- Process lifecycle.
- The real end-to-end system test using URSim, OpenSSH, Dashboard, RTDE when enabled, the gateway, and an OPC UA client.

The gateway system test is the compatibility contract between released distribution versions. Dependency updates should not be accepted unless that complete
pipeline still passes.

## Packaging and release strategy

Each distribution should have independent:

- Package metadata and version.
- README and API documentation.
- Unit-test and formatting workflow.
- Changelog or release notes.
- PyPI project name.
- Source repository once the API has stabilized.

The gateway should use bounded dependency ranges and a repeatable lock or constraints mechanism for release builds. Independent distributions create useful
reuse, but they also introduce compatibility management that does not exist when all modules share one version.

Publishing Dashboard, program discovery, and RTDE together means they share one version and repository. That is a reasonable trade because they serve the same
users and avoids three sets of release metadata, documentation sites, and compatibility ranges. It also means a change to any module releases the distribution,
so CI must test the base installation plus the `sftp`, `rtde`, and `all` extras. Optional dependencies prevent that shared release unit from becoming a
mandatory install of every transport.

During development, package extraction can proceed without immediately publishing production releases:

1. Decouple the candidate module API inside this repository.
1. Copy the decoupled implementation and tests into its package project.
1. Install it into the gateway from a local path or built wheel.
1. Run the gateway's unit and system suites.
1. Publish an initial package release.
1. Replace the local path with a bounded package dependency.
1. Remove the superseded gateway module only after the released dependency passes the complete pipeline.

This sequence avoids a period where behavior exists in neither place and provides a straightforward rollback until the package boundary is proven.

## Recommended extraction order

### 1. Establish the Universal Robots client package

Create `universal_robots_clients` and extract the Dashboard implementation into its `dashboard` module first. It has the clearest independent responsibility,
the smallest dependency surface, and the most obvious external consumers. Its current protocol behavior is already well isolated and tested.

### 2. Add program discovery

Move discovery into `universal_robots_clients.program_discovery`. Before moving it, replace the `Args` dependency with direct local and SFTP APIs and separate
SFTP traversal from SSH connection policy. Publish Paramiko through the `sftp` extra rather than the base dependency set.

### 3. Prove and add RTDE

Implement the required RTDE behavior inside the gateway while the invocation protocol is still changing. Once its reusable boundary is demonstrated by real
tests, move it into `universal_robots_clients.rtde` and define the `rtde` optional extra. Do not create a separate RTDE distribution.

### 4. OPC UA method server

Extract `opcua_method_server` after parameterized invocation clarifies whether the reusable abstraction remains method-oriented or needs declarative variables,
events, and richer node descriptions. Keep it narrow enough to be useful without becoming another general OPC UA framework.

### 5. Simplify the gateway

Once both distributions pass the real system suite, simplify the gateway modules and documentation around their installed APIs. Keep the composition root
explicit even if it becomes short; a small application still benefits from one obvious place where dependencies and policy are assembled.

## Decisions needed before implementation

The following decisions should be made before extraction starts:

- Confirm `universal-robots-clients` as the distribution name and `universal_robots_clients` as the import package after checking registry availability.
- Whether the distributions will use separate repositories immediately or move there after local API stabilization.
- Whether the first Universal Robots client release contains both Dashboard and program discovery or adds `program_discovery` in a second release.
- Which maintained RTDE implementation to use and what narrow API belongs in `universal_robots_clients.rtde`.
- Whether any endpoint or exception types are genuinely shared across the Universal Robots modules.
- The exact optional extras and their supported installation combinations.
- The exact nested method-tree convention for OPC UA folders and objects.
- The supported Python-to-OPC-UA type set in the first release.
- Whether `universal_robots_clients.program_discovery` includes an SFTP connection convenience API in version one.
- The Python support policy and how long Python 3.8.3-compatible releases will be maintained.
- Version ranges and release validation used by the gateway.

## Recommendation

Proceed with the two-distribution architecture. Put Dashboard, program discovery, and eventually RTDE in `universal_robots_clients`, while keeping each
capability in its own namespaced module with independent dependencies and lifecycle. Keep the generic OPC UA server separate because it has no Universal Robots
concern. Begin with Dashboard and program discovery, add RTDE only after the gateway proves its contract, preserve the gateway's real end-to-end test as the
integration contract, and avoid a monolithic robot client abstraction.
