# declarative-opcua-server

`declarative-opcua-server` creates an opinionated synchronous OPC UA server from three flat dictionaries of annotated Python functions. It is intended for small
adapters that need a predictable `Status`, `Parameters`, and `Methods` address space without building nodes manually.

## Installation

```bash
python -m pip install --upgrade pip
python -m pip install declarative-opcua-server
```

Python 3.8.3 and later are supported. The distribution selects a compatible `asyncua` release for the active Python version and caps the final `cryptography`
line that supports Python 3.8. Upgrade the old pip bundled with Python 3.8.3 before installing.

## Example

```python
import time
import typing

import declarative_opcua_server

state = {"height": 10.0}


def read_height() -> float:
    return state["height"]


def write_height(height: float) -> None:
    state["height"] = height


def load_program(program: str) -> str:
    return "Loaded " + program


def list_programs() -> typing.List[str]:
    return ["Main.urp", "Production/PickPart.urp"]


server = declarative_opcua_server.create_server(
    status_interface={"ActualHeight": read_height},
    parameter_interface={"TargetHeight": write_height},
    method_interface={"LoadProgram": load_program, "ListPrograms": list_programs},
    endpoint="opc.tcp://127.0.0.1:4840/",
    namespace="urn:example:robot",
    root_object="Robot",
)

with server:
    while True:
        time.sleep(1.0)
```

`create_server()` returns a plain, unstarted `asyncua.sync.Server`. Callers retain the normal `start()`, `stop()`, and context-manager lifecycle.

## Address space

The example creates:

```text
Objects/
    Robot/
        Status/
            ActualHeight
        Parameters/
            TargetHeight
        Methods/
            LoadProgram(program) -> String
            ListPrograms() -> String[]
```

The selected dictionary defines each callable's role:

- A status getter accepts no arguments and declares a return type. It becomes a polled read-only variable.
- A parameter setter accepts one annotated argument and returns no value. It becomes a writable variable whose accepted writes invoke the setter.
- A method exposes required annotated arguments as OPC UA inputs and an annotated return as an optional output.

Defaulted method arguments are treated as bound application configuration rather than OPC UA inputs. This makes configured `functools.partial` callables useful
without adding wrapper functions.

## Supported annotations

| Python annotation | OPC UA variant type |
| ----------------- | ------------------- |
| `bool`            | `Boolean`           |
| `int`             | `Int64`             |
| `float`           | `Double`            |
| `str`             | `String`            |
| `bytes`           | `ByteString`        |
| `typing.List[T]`  | One-dimensional `T` |

`T` must be one of the supported scalar annotations. Unsupported or unresolved signatures fail during server creation.

## Scope and security

The package intentionally does not provide arbitrary folders, custom node classes, stable NodeId configuration, events, application schemas, or protocol
adapters. Applications requiring a general OPC UA framework should use `asyncua` directly.

The current server defaults to anonymous access and `NoSecurity`. It is suitable for controlled development and isolated industrial networks; certificate and
authentication configuration should be added before use on an untrusted network.

## Development

From this package directory:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests
python -m build
python -m twine check dist/*
```

Tests use a real `asyncua` client to verify browsing, status polling, parameter writes, typed method calls, and lifecycle behavior.

Release history is recorded in the
[changelog](https://github.com/CraigBuilds/ur_dashboard_to_opcua_gateway/blob/main/packages/declarative_opcua_server/CHANGELOG.md). The parent repository
contains the complete validation and publication checklist.
