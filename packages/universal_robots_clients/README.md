# universal-robots-clients

`universal-robots-clients` provides small, protocol-focused modules for interacting with Universal Robots controllers and their program files.

```python
import universal_robots_clients.dashboard as dashboard
import universal_robots_clients.program_discovery as program_discovery

programs = program_discovery.discover_local_programs("/programs")
dashboard.load_program("192.0.2.10", programs[0])
dashboard.play_program("192.0.2.10")
```

The base package uses only the Python standard library. Install the `sftp` extra for Paramiko-backed remote discovery:

```text
python -m pip install "universal-robots-clients[sftp]"
```

Dashboard and program discovery remain separate modules and do not import one another. An RTDE module will be added only after a concrete, tested client
contract has been proven; this package does not currently pretend to provide an RTDE implementation.
