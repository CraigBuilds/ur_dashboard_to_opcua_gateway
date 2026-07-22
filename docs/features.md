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
- Load and start a named program through one convenience operation.
- Pause the running program.
- Stop the active program.
- Read the current program state.
- Reject commands containing line breaks.
- Open one Dashboard TCP connection per command and close it after the response.

### OPC UA

- Create fixed, flat `Status`, `Parameters`, and `Methods` folders beneath `Objects/UR20`.
- Add one no-argument `StartProgram_...()` method for every discovered program.
- Add dynamic `ListPrograms()`, `LoadProgram(program)`, and `RunProgram()` methods for clients that need separate low-level operations.
- Add controller-wide `PauseProgram()` and `StopProgram()` methods.
- Add `RefreshPrograms()` to rediscover the configured catalogue and update generated method nodes without restarting.
- Poll the Dashboard program-state getter into the read-only `Status/ProgramState` variable.
- Poll RTDE connection, controller mode, safety mode, runtime state, stop flags, TCP pose/speed/force, joint position/temperature, speed, and tool I/O into
  typed read-only status variables.
- Write `MoveSpeedPercent` to the robot's global speed slider.
- Treat the two tool digital inputs as portable gripper feedback and expose both tool digital outputs as writable gripper commands.

### Runtime

- Configure local or SFTP catalogue selection through the command line.
- Resolve validated configuration into an immutable `Args` data class.
- Call program discovery and Dashboard operations directly through qualified `universal_robots_clients` module APIs.
- Build flat status, parameter, and method dictionaries directly in the composition root.
- Create an unstarted server through the independently installable `declarative_opcua_server` package.
- Read the SFTP password from `UR_ROBOT_PASSWORD` or an interactive prompt.
- Keep Paramiko in the optional `universal-robots-clients[sftp]` extra and import it only for SFTP connection setup.
- Own one persistent RTDE connection for the complete gateway lifetime and disconnect it after OPC UA status polling stops.
- Keep process startup, `SIGINT`, `SIGTERM`, and shutdown in the main module.
- Run as an installed command or Docker container.

## Current limitations

These are accepted MVP limitations:

- Dashboard responses remain uninterpreted text. Generic lifecycle methods and generated start methods return the final Dashboard response, but do not map
  controller failures to OPC UA status codes.
- A generated start method performs load followed by play without validating the load response.
- `ProgramState` temporarily polls Dashboard rather than RTDE, opening one connection per poll.
- Basic RTDE status and direct controls are implemented, but task-specific register schemas and an atomic parameterized-program invocation handshake are not.
- Gripper signals expose raw tool I/O. Open, closed, object-detected, and fault meanings remain deployment-specific wiring/configuration rather than a portable
  protocol guarantee.
- Robot operations are not serialized across concurrent OPC UA clients.
- OPC UA uses `NoSecurity`.
- SFTP automatically accepts unknown host keys and supports password authentication only.
- There is no application-level operational logging, health endpoint, or metrics.

The MVP should therefore be used on a controlled or isolated network.

## Planned features

The package boundaries and compact composition root are intended to support these additions without redesigning the reusable protocol layers.

### Flat program methods

- Keep one start method per discovered program, with deterministic names such as `StartProgram_Production_PickPart`.
- Preserve unchanged method nodes during explicit refresh, add newly discovered programs, remove missing programs, and reject flattening collisions before
  changing the live interface.
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

The implemented declarative package is intentionally flat. It supports typed method inputs and results, but the first invocation model should still use typed
parameter setters, typed status getters, and no-argument start methods so arguments can be staged and committed atomically:

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
acknowledgement, execution state, and results. Typed method arguments are available for simple commands such as `LoadProgram(program)`, but directly passing a
complete task invocation as method arguments should be considered only after its atomicity, retry, and acknowledgement semantics are designed.

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

Task arguments should be designed and tested as a complete invocation subsystem. The existing speed-slider and tool-I/O parameters are direct controller
controls, not staged program arguments, so they do not imply atomic task invocation.

See [multi-protocol gateway architecture](multi-protocol-gateway-architecture.md) for the proposed separation between Dashboard lifecycle control, RTDE or
alternative invocation transports, protocol-neutral coordination, OPC UA exposure, and reusable package extraction.

### Reusable Python packages

- Maintain the two independently installable public distributions in their own repositories: `declarative_opcua_server` and `universal_robots_clients`.
- Keep `declarative_opcua_server` bounded to three flat interfaces: polled status getters, client-written parameter setters, and typed methods. Do not add
  arbitrary object descriptors, nested schemas, stable NodeId configuration, or events without a concrete consumer that cannot use asyncua directly.
- Keep the implemented source-distribution, wheel, metadata, clean-install, Python 3.8.3, Python 3.12, and URSim checks as release gates.
- Add focused callback-failure, port-binding, and subscription tests before promoting the packages beyond their initial alpha status.
- Keep robot task schemas, invocation identifiers, staged and active values, RTDE mappings, and execution policy in this gateway. Add another OPC UA capability
  later only if the implemented invocation model demonstrates that flat status, parameter, and method functions are insufficient.
- Keep the Dashboard, three URP-discovery, and RTDE client modules focused. Keep task schemas, register allocation, commit and acknowledgement logic, and
  invocation policy in the gateway rather than the package.
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

- Reconsider `python-urx` and other maintained Universal Robots libraries before expanding the robot-integration surface. `rtde_client` currently uses
  `ur-rtde`; continue evaluating its maintenance, compatibility, and operational behavior as the invocation design develops.
- Revisit this decision when the gateway needs persistent connection management, richer robot state, RTDE data, URScript operations, or control beyond the
  Dashboard Server.
- Prefer an established library if it provides tested protocol handling, reconnection, synchronization, error interpretation, and compatibility across relevant
  robot and PolyScope versions.
- Before adoption, assess maintenance activity, licensing, Python 3.8.3 support, native or container dependencies, API stability, security history, and fit with
  the gateway's small qualified package APIs.
- Keep the direct socket implementation inside `universal_robots_clients.dashboard_client` while the MVP only needs a small set of line-oriented commands,
  because a broader robot library would currently add dependency and architectural complexity without replacing much code.

### Implementation decisions to reconsider

- Reconsider replacing the function-local Paramiko import in `universal_robots_clients.urp_discovery_sftp_client` with a top-level namespace import only if SFTP
  becomes mandatory for every package consumer. The current import keeps selector and local discovery imports available without SSH dependencies.
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
