# Reusable Package Extraction

## Purpose

This report proposes extracting three reusable Python packages from the gateway:

1. A generic OPC UA method server that exposes Python callables from a declarative method tree.
1. A Universal Robots Dashboard Server client.
1. A Universal Robots program-discovery library.

The remaining `ur_dashboard_to_opcua_gateway` application would install those packages, apply gateway-specific policy, compose them, and own process
configuration and lifecycle. This direction preserves the current functional architecture while turning three independently useful adapters into small libraries
that other projects can install with `pip`.

This is a proposed target architecture. The packages have not yet been extracted.

## Summary

The current modules already suggest natural package boundaries:

| Current module                          | Proposed package       | Suitability                                                         |
| --------------------------------------- | ---------------------- | ------------------------------------------------------------------- |
| `_04_discover_ur_programs`              | `ur_program_discovery` | Strong, after configuration and SSH policy are decoupled            |
| `_05_control_ur_programs_via_dashboard` | `ur_dashboard_client`  | Strongest and most immediately reusable candidate                   |
| `_07_expose_program_commands_via_opcua` | `opcua_method_server`  | Strong, provided its address-space model remains deliberately small |

The other production modules should remain application code:

- `_01_main` owns this process's entry point and lifecycle.
- `_02_parse_command_line_args` defines this application's combined configuration.
- `_03_compose_gateway` is this application's composition root.
- `_06_combine_program_discovery_and_control` defines gateway-specific command and shortcut policy.

The extraction should reduce the gateway rather than merely move its existing coupling into other repositories. Each package must accept ordinary values and
callables instead of depending on the gateway's `Args`, command registry, module names, OPC UA object names, or process lifecycle.

## Design principles

Each proposed package should:

- Have one coherent responsibility and a small public API.
- Be useful without installing or importing the gateway.
- Accept ordinary Python values, callables, protocols, or standard-library types.
- Avoid embedding gateway-specific defaults such as `UR20`, `ProgramShortcuts`, or the gateway OPC UA namespace.
- Keep transport policy explicit, especially network binding, authentication, host verification, and timeouts.
- Support Python 3.8.3 for as long as the gateway supports it, or publish a compatible version range that the gateway can pin.
- Carry its own focused unit tests and documentation.
- Remain functional unless state and resource ownership provide a concrete benefit.
- Add features only when a real consumer needs them.

The gateway should retain end-to-end tests across the installed packages. Passing each package's unit tests is necessary but does not prove that their released
versions compose correctly.

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

## Universal Robots Dashboard client

### Goal

The Dashboard package would provide ordinary Python functions for communicating with a Universal Robots Dashboard Server. It would be usable by commissioning
scripts, diagnostics, automated tests, manufacturing tools, alternative gateways, and applications that do not use OPC UA.

`ur_dashboard_client` is a clear package name.

### Proposed API

The public API should use direct connection values rather than the gateway's `Args`:

```python
import ur_dashboard_client

state = ur_dashboard_client.get_program_state("192.0.2.10")
loaded = ur_dashboard_client.load_program("192.0.2.10", "Production/PickPart.urp")
started = ur_dashboard_client.play_program("192.0.2.10")
ur_dashboard_client.pause_program("192.0.2.10")
ur_dashboard_client.stop_program("192.0.2.10")
```

The low-level operation should also remain available:

```python
response = ur_dashboard_client.send_command(
    host="192.0.2.10",
    command="robotmode",
    port=29999,
    timeout=5.0,
)
```

An optional immutable endpoint dataclass may be worthwhile when callers repeatedly use the same host, port, and timeout. It should be a convenience layer, not a
requirement for simple function calls.

### Package responsibilities

The package should own:

- Dashboard TCP connection and line framing.
- Greeting and response handling.
- Command injection validation.
- Default Dashboard port and timeout.
- Public functions for supported Dashboard operations.
- Clearly documented transport exceptions.
- Tests for protocol framing, incomplete responses, timeouts, and command construction.

The first release can preserve raw string responses to keep the extraction behaviorally small. Typed response interpretation should be designed later because
different Dashboard commands use different textual success and failure conventions.

### Package exclusions

The package should not know about:

- SFTP or local program discovery.
- OPC UA.
- Gateway command names such as `start` when the Dashboard command is `play`.
- The gateway's `Args`.
- Program shortcuts.
- Gateway-wide concurrency or load-and-start policy.

The gateway can adapt `play_program()` to its public `start` command and decide how to compose `load` followed by `play`.

### Future package features

Likely future additions include:

- More Dashboard commands.
- Typed or classified responses.
- Explicit connection and protocol exception types.
- Persistent connections or sessions.
- Reconnection and stale-session handling.
- Optional command serialization.

Persistent connections should not be part of the initial extraction. The current connection-per-command behavior is simple, stateless, and already tested.

## Universal Robots program discovery

### Goal

The discovery package would find `.urp` files from local filesystems and remote SFTP trees and return deterministic paths relative to a configured program root.
It could support program browsers, deployment checks, backup tools, auditing, synchronization, and gateways using protocols other than OPC UA.

`ur_program_discovery` is a suitable working name. `ur_program_catalog` is another option if the package later includes metadata and refreshable catalogue
objects, but the initial API performs discovery rather than owning long-lived catalogue state.

### Proposed API

Local discovery should require only a path:

```python
import ur_program_discovery

programs = ur_program_discovery.discover_local_programs("/programs")
```

The lowest-level SFTP API should accept an already connected SFTP client:

```python
programs = ur_program_discovery.discover_sftp_programs(
    sftp_client,
    "/programs",
)
```

This boundary keeps authentication, host-key policy, SSH keys, connection timeouts, and connection ownership outside the discovery algorithm. A separately
documented convenience function may open an SFTP connection for simple callers:

```python
programs = ur_program_discovery.discover_programs_over_sftp(
    host="192.0.2.10",
    root="/programs",
    username="robot",
    password=password,
)
```

Paramiko should remain an optional package extra if local discovery can operate without it:

```bash
python -m pip install "ur_program_discovery[sftp]"
```

### Package responsibilities

The package should own:

- Case-insensitive `.urp` identification.
- Recursive local filesystem traversal.
- Recursive SFTP traversal.
- Relative path normalization with forward-slash separators.
- Deterministic sorting.
- Clear errors for invalid roots and unsupported directory entries.

### Package exclusions

The package should not know about:

- The gateway's `Args`.
- Dashboard control.
- OPC UA.
- Password prompting or environment-variable names.
- A mandatory SSH host-key acceptance policy.
- Program execution or shortcut creation.

The convenience SFTP function may expose host-key policy explicitly, but the core traversal function should work with a caller-owned client and therefore avoid
making that decision.

## The remaining gateway application

After extraction, this repository should contain only the policy and wiring that make these libraries into the specific `ur_dashboard_to_opcua_gateway`
application:

- Parse command-line and environment configuration.
- Select local or SFTP discovery.
- Bind Dashboard host, port, and timeout.
- Choose gateway command names.
- Create per-program `load` and `run` shortcuts.
- Define the `UR20` root object, `ProgramShortcuts` structure, OPC UA namespace, and endpoint.
- Compose the installed packages.
- Own signal handling, startup, and shutdown.
- Retain the complete Docker-backed system test.

A possible composition shape is:

```python
import functools

import opcua_method_server
import ur_dashboard_client
import ur_program_discovery

discover_programs = functools.partial(
    ur_program_discovery.discover_local_programs,
    args.programs_folder,
)

dashboard_commands = {
    "load": functools.partial(ur_dashboard_client.load_program, args.dashboard_host),
    "start": functools.partial(ur_dashboard_client.play_program, args.dashboard_host),
    "pause": functools.partial(ur_dashboard_client.pause_program, args.dashboard_host),
    "stop": functools.partial(ur_dashboard_client.stop_program, args.dashboard_host),
    "status": functools.partial(ur_dashboard_client.get_program_state, args.dashboard_host),
}

methods = gateway_commands.create_method_tree(discover_programs, dashboard_commands)

server = opcua_method_server.create_server(
    methods,
    endpoint=args.opcua_endpoint,
    namespace="urn:ur20:program-control",
    root_object="UR20",
)
```

SFTP selection, port binding, timeout binding, and shortcut construction have been omitted from this example for readability. They remain application
composition concerns.

The resulting gateway may be only a small amount of production code, but it still has a meaningful responsibility: it defines how three generic capabilities are
configured and combined into one deployable product.

## Target dependency graph

```text
ur_dashboard_to_opcua_gateway
    +-- opcua_method_server
    |       +-- asyncua
    |
    +-- ur_dashboard_client
    |       +-- Python standard library
    |
    +-- ur_program_discovery
            +-- Python standard library
            +-- paramiko [optional SFTP extra]
```

The three reusable packages should not depend on one another. The gateway is the only layer that understands their combined use.

## Testing ownership

Tests should move with the behavior they verify:

### `opcua_method_server`

- Signature-to-argument conversion.
- Supported scalar and array return metadata.
- Nested method-tree construction.
- Namespace, endpoint, and root-object configuration.
- Callback adaptation.
- Security defaults.

### `ur_dashboard_client`

- Command validation.
- Greeting and response exchanges.
- Connection failures and timeouts.
- Exact Dashboard command formatting.
- Public command functions.

### `ur_program_discovery`

- Local traversal.
- SFTP traversal with fake clients.
- `.urp` filtering.
- Relative path normalization.
- Deterministic ordering.
- Optional dependency behavior.

### `ur_dashboard_to_opcua_gateway`

- Command-line parsing.
- Gateway command and shortcut policy.
- Composition against package APIs.
- Process lifecycle.
- The real end-to-end system test using URSim, OpenSSH, the gateway, and an OPC UA client.

The gateway system test is the compatibility contract between released package versions. Dependency updates should not be accepted unless that complete pipeline
still passes.

## Packaging and release strategy

Each library should have independent:

- Package metadata and version.
- README and API documentation.
- Unit-test and formatting workflow.
- Changelog or release notes.
- PyPI project name.
- Source repository once the API has stabilized.

The gateway should use bounded dependency ranges and a repeatable lock or constraints mechanism for release builds. Independent packages create useful reuse,
but they also introduce compatibility management that does not exist when all modules share one version.

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

### 1. Dashboard client

Extract `ur_dashboard_client` first. It has the clearest independent responsibility, the smallest dependency surface, and the most obvious external consumers.
Its current protocol behavior is already well isolated and tested.

### 2. Program discovery

Extract `ur_program_discovery` second. Before moving it, replace the `Args` dependency with direct local and SFTP APIs and separate SFTP traversal from SSH
connection policy.

### 3. OPC UA method server

Extract `opcua_method_server` third. Its implementation is small, but its public data model requires the most design care. Prove a narrow method-tree API using
the gateway before adding broader OPC UA features.

### 4. Simplify the gateway

Once all three package releases pass the real system suite, simplify the gateway modules and documentation around their installed APIs. Keep the composition
root explicit even if it becomes short; a small application still benefits from one obvious place where dependencies and policy are assembled.

## Decisions needed before implementation

The following decisions should be made before extraction starts:

- Final package and import names.
- Whether the packages will use separate repositories immediately or move there after local API stabilization.
- The exact nested method-tree convention for OPC UA folders and objects.
- The supported Python-to-OPC-UA type set in the first release.
- Whether `ur_program_discovery` includes an SFTP connection convenience API in version one.
- The Python support policy and how long Python 3.8.3-compatible releases will be maintained.
- Version ranges and release validation used by the gateway.

## Recommendation

Proceed with the three-package architecture, beginning with the Dashboard client. The boundaries align with existing responsibilities and produce libraries with
plausible uses outside this gateway. Keep each first release deliberately narrow, preserve the gateway's real end-to-end test as the integration contract, and
avoid generalizing beyond behavior already demonstrated by this application.
