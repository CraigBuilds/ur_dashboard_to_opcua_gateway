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

- Expose generic program and Dashboard methods beneath `Objects/UR20`.
- Mirror program directories beneath `ProgramShortcuts`.
- Add no-argument `load()` and `run()` methods for each discovered program.
- Expose program lists as OPC UA string arrays.

### Runtime

- Configure local or SFTP catalogue selection through the command line.
- Resolve validated configuration into an immutable `Args` data class.
- Represent program discovery and Dashboard operations as configured functions.
- Compose concrete modules without starting them.
- Read the SFTP password from `UR_ROBOT_PASSWORD` or an interactive prompt.
- Keep Paramiko optional and import it only when SFTP discovery is used.
- Keep process startup, `SIGINT`, `SIGTERM`, and shutdown in the main module.
- Run as an installed command or Docker container.

## Current limitations

These are accepted MVP limitations:

- Program shortcuts are generated only at startup.
- Dashboard responses are returned as text rather than interpreted as typed success or failure results.
- `run()` performs load followed by start without validating the load response.
- Robot operations are not serialized across concurrent OPC UA clients.
- OPC UA uses `NoSecurity`.
- SFTP automatically accepts unknown host keys and supports password authentication only.
- There is no application-level operational logging, health endpoint, or metrics.

The MVP should therefore be used on a controlled or isolated network.

## Planned features

The module boundaries are intended to support these additions without redesigning the package.

### Per-program operations

- Replace the term "program shortcuts" with **per-program operations**. If address-space compatibility permits, rename the `ProgramShortcuts` folder to
  `Programs`, represent each discovered program as an object, and rename the generic `programs()` method to `list_programs()` to avoid ambiguity.
- Expand each program object beyond the current no-argument `load()` and `run()` convenience methods. Candidate operations include loading, starting, invoking
  with arguments, and reading whether that specific program is loaded or active.
- Keep controller-wide behavior semantically honest. Dashboard `pause`, `stop`, loaded-program, and current-state commands act on the robot controller rather
  than a named program. They should remain robot-level operations unless a per-program wrapper verifies that the selected program is the active target before
  acting.
- Define one stable application model and derive both the generic controller methods and the per-program OPC UA objects from it, rather than maintaining two
  independently assembled command dictionaries.
- Decide how program additions, removals, and metadata changes update the `Programs` tree. The current startup-only snapshot can remain the MVP behavior, while
  later versions may support an explicit refresh or controlled address-space rebuild.

### Program invocation arguments

Universal Robots programs do not accept ordinary function arguments when loaded or started through the Dashboard Server. Supporting parameterized tasks
therefore requires an invocation protocol shared by the gateway and the robot-side program architecture, not merely extra Dashboard commands.

The design should support at least these robot architectures:

- **Program per task:** each externally visible task maps to a `.urp` program. The gateway stages and commits arguments, loads the selected program, and starts
  it. The program reads the committed invocation values when it begins.
- **Main-loop dispatcher:** one long-running robot program receives a task identifier and arguments, then dispatches to the appropriate internal routine. The
  gateway normally leaves the dispatcher loaded and running, publishes a new invocation, and signals that work is ready.

The application model should describe a task independently of either architecture. A task definition should include:

- A stable task name.
- Its program path or dispatcher task identifier.
- Its execution strategy.
- A typed argument schema containing names, required values, defaults, validation constraints, descriptions, and robot-side mappings.
- Optional timeout, cancellation, and result definitions.

The initial OPC UA design should provide both a convenient high-level API and explicit low-level control. A generated program or task object could resemble:

```text
Programs/
    Production/
        PickPart.urp/
            Arguments/
                Staged/
                    part_id
                    quantity
                Active/
                    part_id
                    quantity
            load()
            start()
            invoke(part_id, quantity)
            commit_arguments()
            invocation_state()
```

The exact node names remain a design decision, but the two levels should behave as follows:

- `invoke(...)` is the easy path. Its OPC UA inputs are generated from the task's argument schema. One call validates the values, creates a committed
  invocation, selects the appropriate robot execution strategy, triggers the task, and returns an invocation identifier or structured status.
- The low-level path lets a client write individual `Arguments/Staged` nodes, inspect or correct them, call `commit_arguments()`, and then use explicit
  `load()`, `start()`, or dispatcher controls. This supports commissioning, diagnostics, PLC-style clients, and integrations that need to own each step.
- Both paths must use the same validation, commit, execution, and status machinery so the convenience API cannot behave differently from manual control.

Individual OPC UA variable writes are not atomic. The argument protocol must prevent a robot from reading a mixture of old and new values:

1. A client writes or supplies a complete staged argument set.
1. The gateway validates the set and assigns an invocation identifier and revision.
1. The gateway publishes an immutable or protected active snapshot, then marks that revision ready as the final step.
1. The robot reads the ready revision and arguments, acknowledges the same invocation identifier, and begins work.
1. The gateway does not overwrite the active snapshot until it is acknowledged, completed, cancelled, or timed out. The first implementation may reject
   concurrent invocations; a queue can be added later.

The gateway should expose invocation status separately from raw Dashboard state. Candidate states include `STAGED`, `READY`, `ACKNOWLEDGED`, `RUNNING`,
`COMPLETED`, `FAILED`, `CANCELLED`, and `TIMED_OUT`, together with the invocation identifier, selected task, validation errors, robot acknowledgement, and any
result values.

OPC UA nodes read by the robot are one possible argument transport, but the application abstraction should not require every robot deployment to use that
mechanism. The invocation coordinator should be able to use interchangeable robot-side adapters, for example:

- OPC UA argument nodes consumed by a robot-side OPC UA client or URCap.
- RTDE input registers.
- Fieldbus or PLC registers.
- Another explicitly designed robot communication mechanism.

The server should generate writable argument nodes and typed `invoke(...)` method inputs from one declarative schema supplied at startup. The schema source
could be gateway configuration, a companion metadata file beside each program, or a separately managed task manifest; this must be decided before
implementation. Program discovery should continue to find `.urp` files without requiring metadata, while parameterized invocation is enabled only for programs
or dispatcher tasks with a valid schema.

The design phase must also resolve:

- The supported OPC UA and robot-side data types, including strings, numbers, booleans, arrays, and bounded values.
- How argument values are encoded and mapped when a robot transport offers only numeric or fixed-width registers.
- Whether values are one-shot, persistent defaults, or both.
- How dispatcher task identifiers are registered and validated.
- How acknowledgements, completion, cancellation, timeout, restart recovery, and duplicate invocation identifiers behave.
- How concurrent OPC UA clients are serialized and authorized.
- Whether results are returned synchronously, published through invocation nodes, or both.
- How schema changes affect existing clients and OPC UA node identifiers.

This feature should be designed and tested as a complete invocation subsystem before adding isolated argument nodes to the current address space.

See [multi-protocol gateway architecture](multi-protocol-gateway-architecture.md) for the proposed separation between Dashboard lifecycle control, RTDE or
alternative invocation transports, protocol-neutral coordination, OPC UA exposure, and reusable package extraction.

### Reusable Python packages

- Evaluate extracting the generic capabilities into independently installable packages: an OPC UA callable-to-method server, a Universal Robots Dashboard
  client, and a Universal Robots program-discovery library.
- Decouple each package from gateway `Args`, UR20-specific OPC UA names, application command dictionaries, shortcut policy, password prompting, and process
  lifecycle.
- Keep this repository as the product-specific composition layer that installs the packages with `pip`, selects configuration and execution policy, builds the
  per-program operation model, and owns startup and shutdown.
- Preserve the real URSim system suite here as the compatibility contract between released package versions.
- Balance reuse against the additional cost of independent versioning, documentation, CI, publishing, dependency constraints, and coordinated upgrades.

See [reusable package extraction](reusable-package-extraction.md) for the proposed package APIs, boundaries, test ownership, release strategy, and extraction
order.

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
- Keep the direct socket implementation while the MVP only needs a small set of line-oriented Dashboard commands, because a broader robot library would
  currently add dependency and architectural complexity without replacing much code.

### Implementation decisions to reconsider

- Reconsider replacing Paramiko's type-checking and function-local imports with a top-level namespace import such as `import paramiko as sshv2` if SFTP becomes
  a required part of every deployment. The current import arrangement keeps Paramiko optional so local-catalogue users can install and run the application
  without its SSH dependencies; a top-level import would make Paramiko mandatory even when SFTP is not used.
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
