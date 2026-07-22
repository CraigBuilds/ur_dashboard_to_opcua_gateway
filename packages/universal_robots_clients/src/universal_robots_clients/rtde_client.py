"""Exchange typed register values through Universal Robots RTDE.

This module is a narrow functional adapter over the optional ``ur-rtde`` dependency. ``connect()`` creates the library's persistent receive and I/O connections
and returns one ``Client`` data holder. The remaining public functions operate on that value to report connection health, reconnect or disconnect both
interfaces, read robot-owned output registers, and write external-client input registers.

The default upper register range is the range intended for external RTDE clients. The selected ``ur-rtde`` recipes expose integer and double registers 42
through 46; callers can explicitly select the lower 18 through 22 range when integrating with an existing fieldbus allocation. Register assignment, Boolean or
string encoding, task schemas, invocation handshakes, and OPC UA naming remain application policy rather than protocol-client behavior.

Install ``universal-robots-clients[rtde]`` to use this module. It depends on ``rtde_receive`` and ``rtde_io`` from ``ur-rtde`` plus standard-library dataclasses,
import handling, threading, and typing. It does not import Dashboard, program discovery, OPC UA, or gateway configuration.
"""

import dataclasses
import importlib
import threading
import typing

__all__ = [
    "Client",
    "connect",
    "disconnect",
    "is_connected",
    "read_output_double_register",
    "read_output_int_register",
    "reconnect",
    "write_input_double_register",
    "write_input_int_register",
]

_LOWER_REGISTER_RANGE = (18, 22)
_UPPER_REGISTER_RANGE = (42, 46)


@dataclasses.dataclass(frozen=True)
class Client:
    """Hold the persistent receive and I/O connections for one robot.

    Used by this module's connection and register functions and by applications that retain an RTDE session.
    """

    _receiver: typing.Any = dataclasses.field(repr=False)
    _writer: typing.Any = dataclasses.field(repr=False)
    _first_register: int
    _last_register: int
    _lock: typing.Any = dataclasses.field(default_factory=threading.RLock, repr=False, compare=False)


def _load_rtde_modules() -> typing.Tuple[typing.Any, typing.Any]:
    """Load the optional ur-rtde modules with an actionable error."""
    try:
        receive_module = importlib.import_module("rtde_receive")
        io_module = importlib.import_module("rtde_io")
    except ImportError as error:
        message = "RTDE support requires the 'universal-robots-clients[rtde]' extra."
        raise RuntimeError(message) from error

    return receive_module, io_module


def _validate_register(client: Client, register: int) -> None:
    """Validate one register against the recipe selected at connection time."""
    if type(register) is not int or not client._first_register <= register <= client._last_register:
        message = f"Register must be an integer from {client._first_register} through {client._last_register}."
        raise ValueError(message)


def connect(host: str, frequency: float = -1.0, use_upper_range_registers: bool = True, verbose: bool = False) -> Client:
    """Connect persistent RTDE receive and I/O interfaces to one robot.

    Used by applications that need typed robot status and parameter exchange, including future parameter support in ``ur_dashboard_to_opcua_gateway``.
    """
    receive_module, io_module = _load_rtde_modules()
    receiver = receive_module.RTDEReceiveInterface(host, frequency, [], verbose, use_upper_range_registers)

    try:
        writer = io_module.RTDEIOInterface(host, verbose, use_upper_range_registers)
    except Exception:
        receiver.disconnect()
        raise

    first_register, last_register = _UPPER_REGISTER_RANGE if use_upper_range_registers else _LOWER_REGISTER_RANGE

    return Client(receiver, writer, first_register, last_register)


def disconnect(client: Client) -> None:
    """Disconnect both interfaces owned by one RTDE client.

    Used by applications during deterministic process or resource shutdown.
    """
    with client._lock:
        try:
            client._writer.disconnect()
        finally:
            client._receiver.disconnect()


def is_connected(client: Client) -> bool:
    """Return whether both RTDE interfaces are connected.

    Used by applications for health checks and reconnect decisions.
    """
    with client._lock:
        return bool(client._receiver.isConnected() and client._writer.isConnected())


def reconnect(client: Client) -> None:
    """Reconnect either RTDE interface that has lost its connection.

    Used by applications that own retry and recovery policy.
    """
    with client._lock:
        if not client._receiver.isConnected() and not client._receiver.reconnect():
            raise ConnectionError("Could not reconnect the RTDE receive interface.")

        if not client._writer.isConnected() and not client._writer.reconnect():
            raise ConnectionError("Could not reconnect the RTDE I/O interface.")


def read_output_int_register(client: Client, register: int) -> int:
    """Read one robot-owned RTDE output integer register.

    Used by status getters and applications that consume robot-published integer values.
    """
    _validate_register(client, register)

    with client._lock:
        return int(client._receiver.getOutputIntRegister(register))


def read_output_double_register(client: Client, register: int) -> float:
    """Read one robot-owned RTDE output double register.

    Used by status getters and applications that consume robot-published floating-point values.
    """
    _validate_register(client, register)

    with client._lock:
        return float(client._receiver.getOutputDoubleRegister(register))


def write_input_int_register(client: Client, register: int, value: int) -> None:
    """Write one external-client RTDE input integer register.

    Used by parameter setters and applications that publish integer values to robot programs.
    """
    _validate_register(client, register)

    with client._lock:
        if not client._writer.setInputIntRegister(register, value):
            raise RuntimeError(f"RTDE rejected the write to input integer register {register}.")


def write_input_double_register(client: Client, register: int, value: float) -> None:
    """Write one external-client RTDE input double register.

    Used by parameter setters and applications that publish floating-point values to robot programs.
    """
    _validate_register(client, register)

    with client._lock:
        if not client._writer.setInputDoubleRegister(register, value):
            raise RuntimeError(f"RTDE rejected the write to input double register {register}.")
