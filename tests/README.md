# Test Suites

Reusable behavior is tested in each package repository, while this directory owns gateway policy, support fixtures, and the cross-package system contract.

## Package tests

- [`declarative-opcua-server`](https://github.com/CraigBuilds/declarative-opcua-server) owns flat-interface validation and real asyncua-client tests.
- [`universal-robots-clients`](https://github.com/CraigBuilds/universal-robots-clients) owns Dashboard, RTDE, local-filesystem, and real OpenSSH/SFTP tests. Its
  CI starts official URSim and talks to the simulator through the real protocol clients.

## Architecture tests

`architecture/` parses gateway production and test modules. It enforces module docstrings, parser help text, namespace-qualified imports, documented public
consumers, and the functional convention that production classes are dataclasses.

## Gateway unit tests

`unit/` tests command-line resolution, direct package binding, flat interface construction, composition, process lifecycle, deterministic program fixtures, and
the system-test runner with fakes and temporary files.

## System tests

`system/` starts the installed gateway, URSim, and OpenSSH, then uses a real OPC UA client to verify local and SFTP configurations, Dashboard program execution,
RTDE-backed status/parameters, and both OPC UA control styles. Direct protocol coverage remains in `universal-robots-clients`.

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
