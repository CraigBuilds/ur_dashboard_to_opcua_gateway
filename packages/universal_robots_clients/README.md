# universal-robots-clients

`universal-robots-clients` provides small, protocol-focused modules for interacting with Universal Robots controllers and their program files.

```python
import universal_robots_clients.dashboard as dashboard
import universal_robots_clients.program_discovery as program_discovery
import universal_robots_clients.rtde as rtde

programs = program_discovery.discover_programs("local", "/programs")
dashboard.load_and_play_program("192.0.2.10", programs[0])

client = rtde.connect("192.0.2.10")
try:
    rtde.write_input_int_register(client, 42, 7)
    value = rtde.read_output_double_register(client, 42)
finally:
    rtde.disconnect(client)
```

The base package uses only the Python standard library. Install optional dependencies for Paramiko-backed SFTP discovery or `ur-rtde`-backed register access:

```text
python -m pip install "universal-robots-clients[sftp]"
python -m pip install "universal-robots-clients[rtde]"
```

The three capability modules do not import one another. `dashboard` owns short-lived Dashboard command connections. `program_discovery` selects local or SFTP
catalogues and also exposes lower-level traversal operations. `rtde` owns a persistent receive/I/O client plus typed integer and double register access; task
schemas, register allocation, invocation handshakes, and robot workflow remain application policy.
