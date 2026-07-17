# declarative-opcua-server

`declarative-opcua-server` creates a synchronous OPC UA server from three flat dictionaries of Python functions:

- Status getters become polled, read-only variables under `Status`.
- Parameter setters become client-writable variables under `Parameters`.
- Functions become typed methods under `Methods`; required annotated arguments are inputs and an annotated return is an output.

```python
import declarative_opcua_server

server = declarative_opcua_server.create_server(
    status_interface={"ToolVoltage": read_tool_voltage},
    parameter_interface={"TargetHeight": write_target_height},
    method_interface={"StartRoutine": start_routine, "LoadProgram": load_program},
)

with server:
    wait_for_process_shutdown()
```

`create_server()` returns a plain, unstarted `asyncua.sync.Server`; callers use its normal `start()`, `stop()`, or context-manager lifecycle. Interfaces are
intentionally flat. Function annotations define OPC UA variable and method argument types, and the package supports `bool`, `int`, `float`, `str`, `bytes`, and
homogeneous `typing.List` values containing those scalar types. The package targets small industrial adapters; applications needing arbitrary OPC UA
address-space models should use `asyncua` directly.
