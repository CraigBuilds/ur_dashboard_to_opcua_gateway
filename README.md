# ur_dashboard_to_opcua_gateway

`ur_dashboard_to_opcua_gateway` discovers Universal Robots programs, controls them through the Dashboard Server, and exposes a compact OPC UA interface.

## Current MVP

- Discover `.urp` programs recursively from a local directory or SFTP.
- List programs and load any selected program through generic OPC UA methods.
- Run, pause, or stop the currently loaded robot program.
- Create one no-argument start method for every program discovered at startup.
- Poll and publish the current Dashboard program state.
- Run as an installed command or container.

The OPC UA address space is deliberately flat:

```text
Objects/
    UR20/
        Status/
            ProgramState
        Parameters/
        Methods/
            ListPrograms() -> String[]
            LoadProgram(program: String) -> String
            RunProgram() -> String
            PauseProgram() -> String
            StopProgram() -> String
            StartProgram_Main()
            StartProgram_Production_PickPart()
```

The generic methods support discovery and low-level lifecycle control, while each generated `StartProgram_...()` method provides a convenient load-then-run
operation. `Parameters` is empty until the RTDE invocation contract is implemented. See [features](docs/features.md) for current limitations and planned
additions.

## Repository

```text
.github/    GitHub Actions CI
code/       Gateway application distribution and Dockerfile
docs/       Architecture, features, package extraction, and testing documentation
packages/   Locally extracted reusable distributions
tests/      Gateway architecture, unit, support, and Docker-backed system tests
```

The two projects beneath `packages/` have independent `pyproject.toml`, `README.md`, `src/`, and `tests/` layouts so they can move to external repositories
without changing their import packages:

- `declarative-opcua-server` / `declarative_opcua_server`
- `universal-robots-clients` / `universal_robots_clients`

The gateway source modules remain in their intended reading order:

```text
_01_main.py
_02_parse_command_line_args.py
_03_compose_gateway.py
```

The application stays deliberately small: argument resolution, product-specific composition, and process lifecycle are its only concerns. Program discovery,
Dashboard communication, and OPC UA hosting live in the reusable packages.

## Install

Install the local package projects before the gateway:

```bash
python -m pip install -e ./packages/declarative_opcua_server
python -m pip install -e ./packages/universal_robots_clients
python -m pip install -e ./code
```

Install SFTP and development dependencies:

```bash
python -m pip install -e "./packages/universal_robots_clients[sftp,rtde,test]"
python -m pip install -e "./packages/declarative_opcua_server[test]"
python -m pip install -e "./code[sftp,test,format]"
```

Python 3.8.3 or later is supported. `declarative-opcua-server` selects `asyncua` 1.1.5 on Python 3.8 and 3.9 and `asyncua` 2.0.1 on Python 3.10 and later.
Paramiko belongs to the optional `universal-robots-clients[sftp]` extra and is imported only for SFTP connection setup. The optional
`universal-robots-clients[rtde]` extra installs `ur-rtde`; RTDE connections are created only when its API is called.

When the packages are published externally, the gateway dependency declarations can resolve them from the package index and the first two local installation
commands will no longer be necessary.

## Run

Use a local or mounted program directory:

```bash
ur_dashboard_to_opcua_gateway --catalog local
```

Local defaults:

```text
Programs folder: /programs
Dashboard host:  127.0.0.1
Dashboard port:  29999
OPC UA endpoint: opc.tcp://0.0.0.0:4840/ur20/
```

Read programs through SFTP:

```bash
export UR_ROBOT_PASSWORD=easybot

ur_dashboard_to_opcua_gateway \
    --catalog sftp \
    --robot-host 192.168.1.2
```

If `UR_ROBOT_PASSWORD` is absent, the command prompts for it. The Dashboard host defaults to `--robot-host` for SFTP configuration and can be overridden with
`--dashboard-host`.

## Docker

The image needs all three distribution sources, so build with the repository root as context:

```bash
docker build -f code/Dockerfile -t ur_dashboard_to_opcua_gateway .
```

Example local deployment:

```bash
docker run --rm \
    --network host \
    -v /programs:/programs:ro \
    ur_dashboard_to_opcua_gateway \
    --catalog local
```

In a normal container, `127.0.0.1` refers to the container itself. Use host networking or set an explicit Dashboard host when the Dashboard Server runs outside
the container.

## Tests

Run both package projects and the gateway without Docker:

```bash
python -m pytest -c tests/pytest.ini -m "not system"
```

Run the complete reusable URSim pipeline on Python 3.10 or later:

```bash
python tests/system/run.py
```

The runner installs all three distributions into an isolated environment, builds the gateway image from the repository root, and verifies local and SFTP
discovery, both OPC UA control styles, Dashboard execution, and RTDE register access against URSim. See [testing](docs/testing.md) for focused commands and
requirements.

## Formatting

The repository uses a 160-column limit:

```bash
python -m black --config code/pyproject.toml code/src packages tests
python -m mdformat --wrap 160 README.md AGENTS.md docs packages/declarative_opcua_server/README.md packages/universal_robots_clients/README.md tests/README.md
```

## Security

The MVP uses OPC UA `NoSecurity` and explicitly enables unknown SFTP host-key trust in the gateway adapter. It is intended for controlled development or
isolated robot networks. Certificates, authentication, verified host keys, and other hardening remain planned features.
