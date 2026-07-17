# Features

## Current MVP

### Program discovery

- Discover `.urp` files recursively.
- Return paths relative to the configured program root.
- Match the `.urp` suffix without regard to letter case.
- Use either a local directory or an SFTP directory.
- Sort program paths before exposing them.

### Dashboard control

- Load a named program.
- Start the loaded program.
- Pause the running program.
- Stop the active program.
- Read the current program state.
- Reject commands containing line breaks.
- Open one Dashboard TCP connection per command and close it after the response.

### OPC UA

- Create fixed, flat `Status`, `Parameters`, and `Methods` folders beneath `Objects/UR20`.
- Add one no-argument `StartProgram_...()` method for every program discovered at startup.
- Add controller-wide `PauseProgram()` and `StopProgram()` methods.
- Poll the Dashboard program-state getter into the read-only `Status/ProgramState` variable.
- Reserve the empty `Parameters` folder for typed RTDE-backed setters.

### Runtime

- Configure local or SFTP catalogue selection through the command line.
- Resolve validated configuration into an immutable `Args` data class.
- Represent program discovery and Dashboard operations as configured functions supplied by `universal_robots_clients`.
- Build flat status, parameter, and method dictionaries into one immutable `GatewayInterfaces` data model.
- Create OPC UA through the independently installable `declarative_opcua_server` package.
- Compose concrete modules without starting them.
- Read the SFTP password from `UR_ROBOT_PASSWORD` or an interactive prompt.
- Keep Paramiko in the optional `universal-robots-clients[sftp]` extra and import it only for SFTP connection setup.
- Keep process startup, `SIGINT`, `SIGTERM`, and shutdown in the main module.
- Run as an installed command or Docker container.

## Current limitations

These are accepted MVP limitations:

- Program start methods are generated only at startup.
- Dashboard responses remain text and are currently discarded by no-result OPC UA methods rather than interpreted as success or failure.
- A generated start method performs load followed by play without validating the load response.
- `ProgramState` temporarily polls Dashboard rather than RTDE, opening one connection per poll.
- RTDE and parameter nodes are not implemented yet.
- Robot operations are not serialized across concurrent OPC UA clients.
- OPC UA uses `NoSecurity`.
- SFTP automatically accepts unknown host keys and supports password authentication only.
- There is no application-level operational logging, health endpoint, or metrics.

The MVP should therefore be used on a controlled or isolated network.

## Planned features

The module boundaries are intended to support these additions without redesigning the package.

### Flat program methods

- Keep one start method per discovered program, with deterministic names such as `StartProgram_Production_PickPart`.
- Decide how program additions, removals, renames, and flattening collisions update the method interface. The current startup snapshot can remain the MVP, while
  later versions may support explicit refresh and controlled server reconstruction.
- Add typed task metadata outside the reusable OPC UA package when parameters are enabled. The package should continue to receive already composed flat
  dictionaries rather than discover programs or understand task schemas itself.
- Keep controller-wide pause, stop, and state behavior separate from generated program methods.

### Program invocation arguments

Universal Robots programs do not accept ordinary function arguments when loaded or started through Dashboard. Supporting parameterized tasks therefore requires
a protocol shared by the gateway and robot-side code, not method input arguments added to Dashboard commands.

The design should support at least these robot architectures:

- **Program per task:** each externally visible task maps to a `.urp` program. The gateway stages and commits arguments, loads the selected program, and starts
  it. The program reads the committed invocation values when it begins.
- **Main-loop dispatcher:** one long-running robot program receives a task identifier and arguments, then dispatches to the appropriate internal routine. The
  gateway normally leaves the dispatcher loaded and running, publishes a new invocation, and signals that work is ready.

The application should describe a task independently of either architecture. A task definition should include:

- A stable task name.
- Its program path or dispatcher task identifier.
- Its execution strategy.
- A typed argument schema containing names, required values, defaults, validation constraints, descriptions, and robot-side mappings.
- Optional timeout, cancellation, and result definitions.

The implemented declarative package is intentionally flat and has no method arguments. The first invocation model should use typed parameter setters, typed
status getters, and no-argument methods:

```text
Status/
    ActiveInvocationId
    InvocationState
    PickPart_QuantityActual
Parameters/
    PickPart_PartId
    PickPart_Quantity
Methods/
    StartProgram_Production_PickPart()
    CancelInvocation()
```

Parameter setters write caller values to RTDE staging registers. A start or invoke method validates that the required parameters have been supplied, assigns an
invocation identifier, commits the staged register set, and then uses the configured execution strategy. Status getters poll RTDE values and publish robot
acknowledgement, execution state, and results. A later convenience API with method arguments should be considered only after this flat contract proves
insufficient; it is not part of `declarative_opcua_server` version 0.1.

Individual OPC UA variable writes are not atomic. The argument protocol must prevent a robot from reading a mixture of old and new values:

1. A client writes or supplies a complete staged argument set.
1. The gateway validates the set and assigns an invocation identifier and revision.
1. The gateway publishes an immutable or protected active snapshot, then marks that revision ready as the final step.
1. The robot reads the ready revision and arguments, acknowledges the same invocation identifier, and begins work.
1. The gateway does not overwrite the active snapshot until it is acknowledged, completed, cancelled, or timed out. The first implementation may reject
   concurrent invocations; a queue can be added later.

The gateway should expose invocation status separately from raw Dashboard state. Candidate states include `STAGED`, `READY`, `ACKNOWLEDGED`, `RUNNING`,
`COMPLETED`, `FAILED`, `CANCELLED`, and `TIMED_OUT`, together with flat status nodes for the invocation identifier, selected task, validation error, robot
acknowledgement, and result values.

OPC UA nodes read by the robot are one possible argument transport, but the application abstraction should not require every robot deployment to use that
mechanism. The invocation coordinator should be able to use interchangeable robot-side adapters, for example:

- OPC UA argument nodes consumed by a robot-side OPC UA client or URCap.
- RTDE input registers.
- Fieldbus or PLC registers.
- Another explicitly designed robot communication mechanism.

The gateway should generate flat parameter, status, and method mappings from one declarative task schema supplied at startup. It supplies ordinary callables to
`declarative_opcua_server` while retaining task validation, invocation state, naming, and robot-transport coordination. The schema source could be gateway
configuration, a companion metadata file, or a task manifest. Program discovery should continue without requiring metadata, while parameterized invocation is
enabled only for tasks with valid schemas and register mappings.

The design phase must also resolve:

- The supported OPC UA and robot-side data types, including strings, numbers, booleans, arrays, and bounded values.
- How argument values are encoded and mapped when a robot transport offers only numeric or fixed-width registers.
- Whether values are one-shot, persistent defaults, or both.
- How dispatcher task identifiers are registered and validated.
- How acknowledgements, completion, cancellation, timeout, restart recovery, and duplicate invocation identifiers behave.
- How concurrent OPC UA clients are serialized and authorized.
- How results are represented through flat status nodes and whether a later synchronous result API is justified.
- How schema changes affect existing clients and OPC UA node identifiers.

This feature should be designed and tested as a complete invocation subsystem before adding isolated parameter setters to the current address space.

See [multi-protocol gateway architecture](multi-protocol-gateway-architecture.md) for the proposed separation between Dashboard lifecycle control, RTDE or
alternative invocation transports, protocol-neutral coordination, OPC UA exposure, and reusable package extraction.

### Reusable Python packages

- Maintain the two local independently installable distributions now implemented beneath `packages/`: `declarative_opcua_server` and `universal_robots_clients`.
- Keep `declarative_opcua_server` bounded to three flat interfaces: polled status getters, client-written parameter setters, and no-argument methods. Do not add
  arbitrary object descriptors, nested schemas, stable NodeId configuration, or events without a concrete consumer that cannot use asyncua directly.
- Complete callback-failure, port-binding, subscription, build-artifact, and clean-install tests before publishing version 0.1 externally.
- Keep robot task schemas, invocation identifiers, staged and active values, RTDE mappings, and execution policy in this gateway. Add another OPC UA capability
  later only if the implemented invocation model demonstrates that flat status, parameter, and method functions are insufficient.
- Keep the implemented Dashboard and program-discovery modules independent. Add `universal_robots_clients.rtde` only after its dependency, connection, getter,
  setter, timeout, and reconnect contracts are proven against URSim.
- Decouple each package from gateway `Args`, UR20-specific OPC UA names, application command dictionaries, shortcut policy, password prompting, and process
  lifecycle.
- Keep this repository as the product-specific composition layer that installs the packages with pip, selects configuration and execution policy, builds flat
  interfaces, and owns process startup and shutdown.
- Preserve the real URSim system suite here as the compatibility contract between released package versions.
- Balance reuse against the additional cost of independent versioning, documentation, CI, publishing, dependency constraints, and coordinated upgrades.

See [reusable package extraction](reusable-package-extraction.md) for the proposed package APIs, boundaries, test ownership, release strategy, and extraction
order.

### Project naming

- Rename the project once RTDE or another second robot-facing protocol works end to end, because `ur_dashboard_to_opcua_gateway` will no longer describe the
  complete product boundary.
- Use `ur_robot_to_opcua_gateway` as the preferred working replacement unless implementation experience reveals a clearer name.
- Make the rename one coordinated migration covering the repository, Python distribution and import package, console command, Docker image, OPC UA server name,
  documentation, tests, and CI references.
- Keep the current name while the product remains the Dashboard-only MVP so published names continue to describe implemented behavior.

See [multi-protocol gateway architecture](multi-protocol-gateway-architecture.md#naming) for the naming rationale and other candidates.

### Reliability and command safety

- Serialize robot-changing operations.
- Make load-and-start atomic.
- Validate Dashboard responses and never start after a failed load.
- Map application and communication failures to useful OPC UA status results.
- Add focused application-contract and system tests for failed loads, transport timeouts, and concurrent calls.

### Security

- Add configurable OPC UA certificates, secure policies, and authentication.
- Require explicit configuration before exposing the service outside a controlled network.
- Verify SFTP hosts through known-host files or pinned fingerprints.
- Support SSH keys and non-root users.
- Add bounded SFTP connection, authentication, and channel timeouts.

### Operations

- Add concise structured logging for startup, discovery, commands, duration, and failures.
- Add health and readiness reporting.
- Add metrics where deployment requirements justify them.

### Third-party robot libraries

- Reconsider `ur_rtde`, `python-urx`, and other maintained Universal Robots libraries before expanding the robot-integration surface.
- Revisit this decision when the gateway needs persistent connection management, richer robot state, RTDE data, URScript operations, or control beyond the
  Dashboard Server.
- Prefer an established library if it provides tested protocol handling, reconnection, synchronization, error interpretation, and compatibility across relevant
  robot and PolyScope versions.
- Before adoption, assess maintenance activity, licensing, Python 3.8.3 support, native or container dependencies, API stability, security history, and fit with
  the gateway's functional module boundaries.
- Keep the direct socket implementation inside `universal_robots_clients.dashboard` while the MVP only needs a small set of line-oriented commands, because a
  broader robot library would currently add dependency and architectural complexity without replacing much code.

### Implementation decisions to reconsider

- Reconsider replacing the function-local Paramiko import in `universal_robots_clients.program_discovery` with a top-level namespace import only if SFTP becomes
  mandatory for every package consumer. The current import keeps local discovery available without SSH dependencies.
- Reconsider maintaining a persistent Dashboard connection, connection pool, or stateful Dashboard session if command frequency, connection latency, or
  multi-command operations justify it. The MVP deliberately opens one connection per command because this is stateless, isolates failed exchanges, and avoids
  connection ownership, locking, stale-session detection, reconnection, and shutdown lifecycle concerns. Any persistent design should define serialization,
  reconnect behaviour, greeting handling, idle timeouts, failure recovery, and clean process shutdown before replacing the current behaviour.

### Catalogue and API extensions

- Refresh the catalogue without restarting the gateway.
- Add additional discovery backends selected by `discover_programs()`.
- Add optional program metadata.
- Add write, upload, delete, or scheduling functions only when a concrete use case requires them.

These planned items are not exposed by the current command line or OPC UA address space.
