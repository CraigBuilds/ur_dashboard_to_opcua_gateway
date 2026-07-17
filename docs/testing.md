# Testing

## Test ownership

Executable tests are organized by both distribution ownership and scope:

- `packages/declarative_opcua_server/tests/` verifies the standalone OPC UA API with validation tests and a real asyncua client.
- `packages/universal_robots_clients/tests/` verifies Dashboard framing and local/SFTP discovery with deterministic fakes.
- `tests/architecture/` statically enforces conventions across all three distributions and their tests.
- `tests/unit/` verifies gateway configuration, adapters, interface policy, composition, and lifecycle.
- `tests/system/` verifies the installed distributions together with real URSim, OpenSSH, the gateway container, and an OPC UA client.

`tests/support/` contains shared fixtures and is not another test type.

## Installation

Install the local distributions and development tools from the repository root:

```bash
python -m pip install -e "./packages/declarative_opcua_server[test]"
python -m pip install -e "./packages/universal_robots_clients[sftp,test]"
python -m pip install -e "./code[sftp,test,format]"
```

Run every non-container test:

```bash
python -m pytest -c tests/pytest.ini -m "not system"
```

Focused package and gateway commands are:

```bash
python -m pytest -c tests/pytest.ini packages/declarative_opcua_server/tests
python -m pytest -c tests/pytest.ini packages/universal_robots_clients/tests
python -m pytest -c tests/pytest.ini tests/architecture tests/unit
```

The non-container suite supports Python 3.8.3 and later. CI runs it on Python 3.8.3 with asyncua 1.1.5 and Python 3.12 with asyncua 2.0.1.

## Coverage

The non-container tests cover:

- Declarative status polling, scalar and list values, parameter writes, methods, partial signatures, lifecycle, and flat-interface validation through a real OPC
  UA client.
- Dashboard line injection, greeting and response framing, endpoint forwarding, and exact named command construction.
- Local and caller-owned SFTP traversal, filtering, normalization, sorting, optional Paramiko setup, and explicit host-key policy.
- Command-line defaults, overrides, credentials, validation, and package-adapter delegation.
- Flat per-program method naming, collision detection, load-before-play policy, controller methods, and status composition.
- OPC UA application identity forwarding, composition-root wiring, signal handling, and clean managed-server shutdown.
- Reproducible no-motion URP fixtures and system-test runner argument handling.
- Module docstrings, parser help, namespace imports, documented public consumers, and dataclass-only production classes.

Planned reliability tests include callback failure status mapping, port binding, polling failures, Dashboard timeouts, failed load responses, concurrent robot
operations, and RTDE disconnect behavior.

## System tests

Run the prepared workflow on Python 3.10 or later:

```bash
python tests/system/run.py
```

The runner:

- Finds a supported interpreter.
- Keeps its environment and pytest cache outside the repository.
- Copies and installs both reusable packages and the gateway as separate distributions.
- Checks for Linux `amd64` Docker.
- Pulls the pinned URSim image unless `--no-pull` is used.
- Builds the gateway with the repository root as Docker context.
- Runs both local and SFTP catalogue arrangements.

Select a catalogue or interpreter with:

```bash
python tests/system/run.py --catalog local
python tests/system/run.py --catalog sftp
python tests/system/run.py --python "/path/to/python3.12"
```

Install and collect without Docker:

```bash
python tests/system/run.py --collect-only
```

For each arrangement, a real OPC UA client browses the flat `Status`, `Parameters`, and `Methods` folders, verifies the discovered program methods, observes a
polled Dashboard state, starts `Main.urp`, pauses and stops it, starts `Production/PickPart.urp`, and confirms the loaded and playing state directly through
URSim.

The local arrangement mounts programs and shares the URSim network namespace. The SFTP arrangement uses a private Docker network containing the gateway, URSim,
and OpenSSH. The same OPC UA contract must pass in both cases.

## Formatting

```bash
python -m black --config code/pyproject.toml --check code/src packages tests
python -m mdformat --check --wrap 160 README.md AGENTS.md docs packages/declarative_opcua_server/README.md packages/universal_robots_clients/README.md tests/README.md
```

## CI

GitHub Actions installs all three distributions separately. Unit jobs run package, architecture, and gateway tests on Python 3.8.3 and 3.12. A Python 3.8.3
quality job checks all Python and Markdown sources, while a Python 3.12 system job runs the Docker-backed compatibility pipeline.
