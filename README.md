# ur_dashboard_to_opcua_gateway

`ur_dashboard_to_opcua_gateway` exposes Universal Robots program files and Dashboard Server controls through OPC UA.

## Current MVP

The first version deliberately has a small feature set:

- Discover `.urp` programs from a local directory or through SFTP.
- List discovered programs through OPC UA.
- Load, start, pause, and stop robot programs.
- Read the current Dashboard program state.
- Create `load()` and `run()` shortcuts for each program found at startup.
- Run locally or in a container.

The OPC UA address space is:

```text
Objects/
    UR20/
        programs()
        load(program)
        start()
        pause()
        stop()
        status()
        ProgramShortcuts/
            Main.urp/
                load()
                run()
            Production/
                PickPart.urp/
                    load()
                    run()
```

See [features](docs/features.md) for current limitations and planned additions.

## Repository

```text
README.md
.github/   GitHub Actions CI
code/      Python package and gateway Dockerfile
docs/      Architecture, features, and testing documentation
tests/     Unit tests, system tests, and test containers
```

The source modules are numbered in their intended reading order:

```text
_01_main.py
_02_parse_command_line_args.py
_03_compose_gateway.py
_04_discover_ur_programs.py
_05_control_ur_programs_via_dashboard.py
_06_combine_program_discovery_and_control.py
_07_expose_program_commands_via_opcua.py
```

## Install

From the repository root, install local catalogue support:

```bash
python -m pip install ./code
```

Install SFTP support:

```bash
python -m pip install "./code[sftp]"
```

Install a development environment:

```bash
python -m pip install -e "./code[test,format]"
```

Python 3.8.3 or later is supported. Python 3.8 and 3.9 install `asyncua` 1.1.5, while Python 3.10 and later install `asyncua` 2.0.1.

The Docker image continues to use Python 3.12.

## Run

Use a local or mounted programs directory:

```bash
ur_dashboard_to_opcua_gateway --catalog local
```

Defaults:

```text
Programs folder: /programs
Dashboard host:  127.0.0.1
Dashboard port:  29999
OPC UA endpoint: opc.tcp://0.0.0.0:4840/ur20/
```

Read programs from a robot through SFTP:

```bash
export UR_ROBOT_PASSWORD=easybot

ur_dashboard_to_opcua_gateway \
    --catalog sftp \
    --robot-host 192.168.1.2
```

If `UR_ROBOT_PASSWORD` is absent, the command prompts for the password. Use `--dashboard-host` when the Dashboard Server is at a different address.

## Docker

Build from the `code` directory:

```bash
docker build -t ur_dashboard_to_opcua_gateway code
```

Example local catalogue deployment:

```bash
docker run --rm \
    --network host \
    -v /programs:/programs:ro \
    ur_dashboard_to_opcua_gateway \
    --catalog local
```

In a normal container, `127.0.0.1` refers to the container itself. Use host networking or provide an explicit Dashboard host when the Dashboard Server runs
outside the container.

## Tests

Run the Python 3.8-compatible unit suite:

```bash
python -m pytest -c tests/pytest.ini -m "not system"
```

Install the system-test dependencies and run the complete suite on Python 3.10 or later:

```bash
python -m pip install -e "./code[system-test]"
python -m pytest -c tests/pytest.ini
```

Or let the system-test runner prepare an isolated environment, check Docker, pull URSim, and run both real catalogue paths:

```bash
python tests/run_system_tests.py
```

When starting the runner with an older Python, select a Python 3.10 or later executable explicitly:

```bash
python tests/run_system_tests.py --python "/path/to/python3.12"
```

The system tests require Python 3.10 or later, Docker, and a Linux `amd64` environment for the pinned URSim image. See [testing](docs/testing.md) for details.

## Formatting

The repository uses a 160-column limit:

```bash
python -m black --config code/pyproject.toml code/src tests
python -m mdformat --wrap 160 README.md docs
```

## Security

The MVP uses OPC UA `NoSecurity` and automatically accepts unknown SSH host keys. It is intended for controlled development or isolated robot networks.
Certificates, authentication, host verification, and other hardening are planned features rather than part of this first version.
