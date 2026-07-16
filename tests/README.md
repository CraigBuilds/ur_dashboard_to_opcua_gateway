# Test Suites

The repository has three executable test types. Folder selection makes each type independently runnable, while the `system` marker keeps Docker-backed tests out
of the Python 3.8-compatible default suite.

## Architecture tests

`architecture/` contains static repository checks. These tests parse source files with `ast` and enforce project-wide conventions such as module docstrings,
argument help text, namespace-qualified imports, documented public consumers, and the functional rule that production classes are dataclasses.

They do not execute the gateway or require external services:

```bash
python -m pytest -c tests/pytest.ini tests/architecture
```

## Unit tests

`unit/` contains isolated component, behavior, validation, composition, protocol, and lifecycle tests. External boundaries are represented by temporary files,
monkeypatches, and deterministic fakes, so these tests require neither Docker nor network access:

```bash
python -m pytest -c tests/pytest.ini tests/unit
```

## System tests

`system/` contains the Docker-backed full-system tests and everything private to that harness. The suite builds and starts the gateway, URSim, and OpenSSH, then
uses a real OPC UA client to verify both local and SFTP catalogue paths through to Dashboard program execution.

These tests also serve as the current integration and end-to-end coverage. There is no separate integration suite because the project does not yet have a useful
middle-sized boundary that warrants another category.

Run the prepared system-test workflow with:

```bash
python tests/system/run.py
```

## Support code

`support/` is not a fourth test type. It contains deterministic program fixtures and polling helpers shared by executable suites. Likewise, `system/containers/`
and `system/docker/` are implementation details of the system-test harness rather than independently collected tests.

## Complete layout

```text
tests/
    architecture/    Repository structure and convention checks
    unit/            Fast isolated tests
    system/          Docker-backed integration and end-to-end tests
        containers/  Python wrappers around disposable services
        docker/      Docker build contexts owned by the system harness
    support/         Shared fixtures and test utilities
    pytest.ini       Test discovery, paths, and markers
```

Run every non-container test with:

```bash
python -m pytest -c tests/pytest.ini -m "not system"
```

See [the complete testing guide](../docs/testing.md) for installation, formatting, Docker requirements, and CI behavior.
