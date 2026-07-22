# universal-robots-clients

`universal-robots-clients` provides small, functional Python clients for Universal Robots controller protocols and URP program catalogues. Each capability is an
explicit module, so call sites retain context and applications install only the optional protocol dependencies they use.

## Installation

```bash
python -m pip install --upgrade pip
python -m pip install universal-robots-clients
```

Install optional SFTP or RTDE support:

```bash
python -m pip install "universal-robots-clients[sftp]"
python -m pip install "universal-robots-clients[rtde]"
python -m pip install "universal-robots-clients[all]"
```

Python 3.8.3 and later are supported. Upgrade the old pip bundled with Python 3.8.3 before installing optional binary dependencies.

## Modules

| Module                       | Responsibility                                            | Optional dependency |
| ---------------------------- | --------------------------------------------------------- | ------------------- |
| `dashboard_client`           | Send Dashboard Server commands and program operations     | None                |
| `urp_discovery_client`       | Select local or SFTP discovery from runtime configuration | SFTP when selected  |
| `urp_discovery_local_client` | Discover URP files through a local filesystem             | None                |
| `urp_discovery_sftp_client`  | Discover URP files through caller-owned or managed SFTP   | Paramiko            |
| `rtde_client`                | Maintain RTDE connections and exchange typed registers    | ur-rtde             |

The package root deliberately re-exports no operations. Importing capability modules keeps ownership visible:

```python
import universal_robots_clients.dashboard_client as dashboard_client

response = dashboard_client.load_and_play_program("192.0.2.10", "Production/PickPart.urp")
```

### Dashboard client

Every Dashboard command uses one short-lived TCP connection. Responses are returned as stripped protocol text because Dashboard success and failure formats vary
by command.

```python
import universal_robots_clients.dashboard_client as dashboard_client

dashboard_client.load_program("192.0.2.10", "Main.urp")
dashboard_client.play_program("192.0.2.10")
state = dashboard_client.get_program_state("192.0.2.10")
dashboard_client.pause_program("192.0.2.10")
dashboard_client.stop_program("192.0.2.10")
```

`send_command()` remains available for Dashboard operations that do not yet have a named helper.

### URP discovery clients

Use the selector when configuration chooses the backend at runtime:

```python
import universal_robots_clients.urp_discovery_client as urp_discovery_client

programs = urp_discovery_client.discover_programs("local", "/programs")
```

Use a backend directly when it is already known:

```python
import universal_robots_clients.urp_discovery_local_client as urp_discovery_local_client
import universal_robots_clients.urp_discovery_sftp_client as urp_discovery_sftp_client

local_programs = urp_discovery_local_client.discover_programs("/programs")
sftp_programs = urp_discovery_sftp_client.connect_and_discover_programs(
    host="192.0.2.10",
    root="/programs",
    username="root",
    password="secret",
)
```

Both backends recursively find case-insensitive `.urp` files, return paths relative to the configured root, normalize separators to `/`, and sort the result.
Advanced callers can pass an existing connected SFTP client to `urp_discovery_sftp_client.discover_programs()`.

### RTDE client

The RTDE module wraps the optional `ur-rtde` receive and I/O interfaces behind a functional API. A `Client` data class owns the persistent resources; module
functions own all behavior.

```python
import universal_robots_clients.rtde_client as rtde_client

client = rtde_client.connect("192.0.2.10")

try:
    rtde_client.write_input_int_register(client, 42, 7)
    rtde_client.write_input_double_register(client, 43, 1.25)
    counter = rtde_client.read_output_int_register(client, 42)
    result = rtde_client.read_output_double_register(client, 43)
finally:
    rtde_client.disconnect(client)
```

Upper registers 42 through 46 are selected by default for external RTDE clients. Pass `use_upper_range_registers=False` to select registers 18 through 22.
Register allocation, invocation handshakes, and robot-side program conventions remain application policy.

## Security

- Dashboard and RTDE connections are unencrypted controller protocols and should be used on a controlled robot network.
- SFTP loads system host keys and rejects unknown hosts by default.
- `trust_unknown_host_keys=True` is an explicit opt-in intended only for controlled environments.
- Applications own credential storage, authorization, retry, and command-success policy.

## Development

From this package directory:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests
python -m mypy
python -m build
python -m twine check dist/*
```

Unit tests do not require a robot. The parent gateway repository also runs a real URSim contract for Dashboard execution, SFTP discovery, and RTDE register
access.

Release history is recorded in the
[changelog](https://github.com/CraigBuilds/ur_dashboard_to_opcua_gateway/blob/main/packages/universal_robots_clients/CHANGELOG.md). The parent repository
contains the complete validation and publication checklist.
