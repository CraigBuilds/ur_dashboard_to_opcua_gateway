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

### Reliability and command safety

- Serialize robot-changing operations.
- Make load-and-start atomic.
- Validate Dashboard responses and never start after a failed load.
- Map application and communication failures to useful OPC UA status results.
- Add focused failure, timeout, and concurrency tests.

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
