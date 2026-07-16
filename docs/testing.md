# Testing

## Test types

The executable tests are organized by scope:

- `tests/architecture/` statically enforces repository and API conventions.
- `tests/unit/` exercises components and behavior in isolation with deterministic fakes.
- `tests/system/` verifies the complete gateway with real URSim, OpenSSH, gateway, and OPC UA containers.

`tests/support/` contains shared fixtures and utilities; it is support code, not a separate test type. The system suite currently provides both integration and
end-to-end coverage, so there is no separate integration-test folder. See [the test-suite README](../tests/README.md) for the complete layout and focused
commands.

## Commands

Install the Python 3.8-compatible unit-test and formatting dependencies from the repository root:

```bash
python -m pip install -e "./code[test,format]"
```

The unit suite uses deterministic transport fakes and does not require the optional SFTP dependency. Install `./code[sftp,test,format]` when developing or
manually exercising the SFTP catalogue as well.

Run the non-container suite:

```bash
python -m pytest -c tests/pytest.ini -m "not system"
```

On Python 3.10 or later, install the system-test dependencies:

```bash
python -m pip install -e "./code[system-test]"
```

Run all tests:

```bash
python -m pytest -c tests/pytest.ini
```

Run only the system tests:

```bash
python -m pytest -c tests/pytest.ini -m system
```

The preferred one-command route is:

```bash
python tests/system/run.py
```

The runner:

- Finds Python 3.10 or later.
- Keeps a reusable virtual environment and pytest cache in the operating-system user cache rather than the repository.
- Installs the package and `system-test` dependencies from a temporary source copy.
- Checks that Docker is running Linux `amd64` containers.
- Pulls the exact URSim image pinned by the test harness.
- Runs both local and SFTP catalogue paths.

If the runner is started with an older Python and cannot find a newer interpreter automatically, provide one explicitly:

```bash
python tests/system/run.py --python "/path/to/python3.12"
```

Select one catalogue path:

```bash
python tests/system/run.py --catalog local
python tests/system/run.py --catalog sftp
```

Install dependencies and verify test collection without Docker:

```bash
python tests/system/run.py --collect-only
```

Use `--skip-install` to reuse the prepared environment without asking pip to check dependencies, or `--no-pull` to let Testcontainers pull URSim when needed.
Additional pytest arguments can be placed after `--`.

## Architecture and unit coverage

The non-container tests cover:

- Local and SFTP command-line defaults, overrides, password sources, and required-value validation.
- Local and recursive SFTP program discovery, URP filtering, relative paths, deterministic ordering, SSH setup, and invalid discovery configuration.
- Dashboard command injection rejection, line-oriented socket exchanges, incomplete-response failures, endpoint binding, and exact protocol command mapping.
- Application command registry construction, per-program shortcut binding, load-before-start sequencing, and catalogue return-type validation.
- Gateway composition, executable entry-point wiring, signal handler installation, and clean server-context shutdown.
- OPC UA method argument metadata, array return metadata, folder caching, namespace creation, endpoint configuration, and adapter wiring.
- Deterministic, reproducible, readable no-motion URP fixture generation.
- Reusable system-test runner interpreter validation, catalogue selection, collect-only mode, and pytest argument forwarding.
- Architecture checks for required top-level docstrings, parser help messages, namespace imports, documented public consumers, and dataclass-only production
  classes.

The reliability and security cases listed in [planned features](features.md#planned-features) are intentionally deferred.

## System tests

The system suite uses real interfaces:

- Official URSim e-Series configured as a UR20.
- Deterministic PolyScope-compatible programs generated locally with a no-motion `Wait` node.
- A disposable OpenSSH server with its SFTP subsystem.
- The gateway Docker image built from `code/`.
- A real `asyncua` OPC UA client.

For each catalogue path, the client discovers the generated programs, loads `Main.urp`, starts it through the generic OPC UA `start()` method, and verifies that
URSim reports `PLAYING`. It then pauses and stops the program, invokes the generated `Production/PickPart.urp/run()` shortcut, confirms that URSim loaded
`PickPart.urp`, and again verifies the `PLAYING` state before stopping the robot.

Two arrangements run the same OPC UA contract:

```text
Local catalogue:
    Gateway shares the URSim network namespace.
    Program files are mounted directly.
    Dashboard host is 127.0.0.1.

SFTP catalogue:
    Gateway, URSim, and OpenSSH share a private Docker network.
    Program discovery uses SFTP.
    Program control uses URSim Dashboard Server.
```

Python 3.10 or later, Docker, and a Linux `amd64` environment are required. Install
[Docker Desktop on Windows](https://docs.docker.com/desktop/setup/install/windows-install/) or [Docker Engine on Linux](https://docs.docker.com/engine/install/)
and make sure its daemon is running before starting the suite. The pinned URSim image occupies approximately 3.2 GB once unpacked, and the first run also
downloads Python packages and base images used to build the gateway and OpenSSH test containers. Later runs reuse normal pip and Docker caches.

Python versions below 3.10 skip this suite at module collection time because the current container harness depends on `testcontainers` releases that no longer
support those Python versions.

## Formatting

```bash
python -m black --config code/pyproject.toml --check code/src tests
python -m mdformat --check --wrap 160 README.md AGENTS.md docs tests/README.md
```

## CI

GitHub Actions runs architecture and unit tests and checks the installed command on Python 3.8.3 and 3.12. A Python 3.8.3 quality job checks Python formatting
plus all maintained Markdown documentation, including `AGENTS.md` and `tests/README.md`, while a separate Python 3.12 job runs the Docker-backed system suite.
