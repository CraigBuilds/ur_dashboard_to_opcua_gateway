# declarative-opcua-server

`declarative-opcua-server` creates a synchronous OPC UA server from three flat dictionaries of Python functions:

- Status getters become polled, read-only variables under `Status`.
- Parameter setters become client-writable variables under `Parameters`.
- Commands become no-argument methods under `Methods`.

```python
import declarative_opcua_server

server = declarative_opcua_server.create_server(
    status_interface={"ToolVoltage": read_tool_voltage},
    parameter_interface={"TargetHeight": write_target_height},
    method_interface={"StartRoutine": start_routine},
)

with server:
    wait_for_process_shutdown()
```

Interfaces are intentionally flat. Function annotations define OPC UA types, and the package supports `bool`, `int`, `float`, `str`, `bytes`, and homogeneous
`typing.List` values containing those scalar types. The package targets small industrial adapters; applications needing arbitrary OPC UA address-space models
should use `asyncua` directly.
