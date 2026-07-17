# Test Suites

Reusable behavior is tested inside each package project, while this directory owns cross-repository conventions, gateway policy, support fixtures, and the full
system contract.

## Package tests

```text
packages/declarative_opcua_server/tests/  Real-client OPC UA API and validation tests
packages/universal_robots_clients/tests/  Dashboard and program-discovery tests
```

Both are collected by `tests/pytest.ini` so one command runs the complete non-container contract.

## Architecture tests

`architecture/` parses every production and test module across all three distributions. It enforces module docstrings, parser help text, namespace-qualified
imports, documented public consumers, and the functional convention that production classes are dataclasses.

## Gateway unit tests

`unit/` tests command-line resolution, package adapters, flat interface construction, composition, process lifecycle, deterministic program fixtures, and the
system-test runner with fakes and temporary files.

## System tests

`system/` builds and starts the three installed distributions, URSim, and OpenSSH, then uses a real OPC UA client to verify local and SFTP discovery through to
Dashboard program execution. These tests are both integration and end-to-end coverage.

## Layout

```text
tests/
    architecture/    Repository and API convention checks
    unit/            Gateway policy and composition tests
    system/          Docker-backed compatibility and end-to-end tests
        containers/  Disposable service wrappers
        docker/      OpenSSH test image
    support/         Shared deterministic fixtures and waiting helpers
    pytest.ini       Package and gateway discovery paths and markers
```

Run everything except Docker:

```bash
python -m pytest -c tests/pytest.ini -m "not system"
```

Run the prepared real pipeline:

```bash
python tests/system/run.py
```

See [the complete testing guide](../docs/testing.md) for installation, focused commands, Docker requirements, and CI behavior.
