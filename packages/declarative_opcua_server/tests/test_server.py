"""Verify the declarative OPC UA package through its public API and a real client."""

import contextlib
import functools
import socket
import time
import typing

import asyncua.sync
import declarative_opcua_server
import pytest


def _endpoint() -> str:
    """Reserve and release a local port for one short-lived OPC UA server."""
    listener = socket.socket()

    with contextlib.closing(listener):
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    return f"opc.tcp://127.0.0.1:{port}/"


def _child(parent: asyncua.sync.SyncNode, namespace: int, name: str) -> asyncua.sync.SyncNode:
    """Return one namespaced child node."""
    return parent.get_child([f"{namespace}:{name}"])


def _wait_for_value(node: asyncua.sync.SyncNode, expected: object) -> None:
    """Wait briefly for the package polling thread to publish one value."""
    deadline = time.monotonic() + 3.0

    while time.monotonic() < deadline:
        if node.read_value() == expected:
            return

        time.sleep(0.05)

    assert node.read_value() == expected


def test_interfaces_work_through_a_real_opcua_client() -> None:
    """Poll status, forward parameter writes, and invoke methods through OPC UA."""
    state: typing.Dict[str, object] = {"voltage": 24.0, "pose": [1.0, 2.0], "height": None, "started": False, "loaded": None}

    def read_voltage() -> float:
        """Read the simulated status value."""
        return typing.cast(float, state["voltage"])

    def read_pose() -> typing.List[float]:
        """Read one simulated vector status value."""
        return typing.cast(typing.List[float], state["pose"])

    def write_height(height: int) -> None:
        """Write one simulated parameter value."""
        state["height"] = height

    def start() -> None:
        """Run one simulated method."""
        state["started"] = True

    def load(program: str) -> str:
        """Load one named simulated program."""
        state["loaded"] = program

        return f"Loaded {program}"

    def list_programs() -> typing.List[str]:
        """List simulated programs."""
        return ["Main.urp", "Pick.urp"]

    endpoint = _endpoint()
    namespace_uri = "urn:declarative-opcua-server:test"
    server = declarative_opcua_server.create_server(
        status_interface={"ToolVoltage": read_voltage, "TcpPose": read_pose},
        parameter_interface={"TargetHeight": write_height},
        method_interface={"StartRoutine": start, "LoadProgram": load, "ListPrograms": list_programs},
        endpoint=endpoint,
        namespace=namespace_uri,
        root_object="TestApplication",
    )
    assert type(server) is asyncua.sync.Server

    with server:
        with asyncua.sync.Client(endpoint) as client:
            namespace = client.get_namespace_index(namespace_uri)
            root = _child(client.nodes.objects, namespace, "TestApplication")
            status = _child(root, namespace, "Status")
            parameters = _child(root, namespace, "Parameters")
            methods = _child(root, namespace, "Methods")
            voltage = _child(status, namespace, "ToolVoltage")
            pose = _child(status, namespace, "TcpPose")
            height = _child(parameters, namespace, "TargetHeight")
            start_method = _child(methods, namespace, "StartRoutine")
            load_method = _child(methods, namespace, "LoadProgram")
            list_method = _child(methods, namespace, "ListPrograms")
            _wait_for_value(voltage, 24.0)
            _wait_for_value(pose, [1.0, 2.0])
            state["voltage"] = 48.0
            typing.cast(typing.List[float], state["pose"]).append(3.0)
            _wait_for_value(voltage, 48.0)
            _wait_for_value(pose, [1.0, 2.0, 3.0])
            height.write_value(125)
            methods.call_method(start_method)
            assert methods.call_method(load_method, "Main.urp") == "Loaded Main.urp"
            assert methods.call_method(list_method) == ["Main.urp", "Pick.urp"]

    assert state["height"] == 125
    assert state["started"] is True
    assert state["loaded"] == "Main.urp"


def test_partial_signatures_and_supported_scalar_types_are_resolved() -> None:
    """Resolve annotations from configured partials without exposing bound arguments."""
    captured: typing.List[str] = []

    def read_value(source: typing.Dict[str, str]) -> str:
        """Read one configured string."""
        return source["value"]

    def write_value(target: typing.List[str], value: str) -> None:
        """Write one configured string."""
        target.append(value)

    server = declarative_opcua_server.create_server(
        status_interface={"State": functools.partial(read_value, {"value": "READY"})},
        parameter_interface={"Name": functools.partial(write_value, captured)},
        method_interface={},
        endpoint=_endpoint(),
    )

    with server:
        time.sleep(0.15)


@pytest.mark.parametrize(
    ("interfaces", "message"),
    [
        (({"Bad": lambda value: value}, {}, {}), "must accept no arguments"),
        (({"Bad": lambda: None}, {}, {}), "must declare a return type"),
        (({}, {"Bad": lambda: None}, {}), "exactly one argument"),
        (({}, {}, {"Bad": lambda value: None}), "must annotate argument"),
    ],
)
def test_invalid_interface_signatures_fail_during_creation(interfaces: typing.Tuple[typing.Dict[str, typing.Callable[..., object]], ...], message: str) -> None:
    """Reject functions that do not satisfy their selected interface role."""
    status_interface, parameter_interface, method_interface = interfaces

    with pytest.raises(TypeError, match=message):
        declarative_opcua_server.create_server(
            status_interface=status_interface, parameter_interface=parameter_interface, method_interface=method_interface, endpoint=_endpoint()
        )


def test_nested_interfaces_are_rejected() -> None:
    """Keep the package contract flat instead of interpreting nested dictionaries."""
    with pytest.raises(TypeError, match="must be callable"):
        declarative_opcua_server.create_server(status_interface={"Nested": {"Value": lambda: 1}}, parameter_interface={}, method_interface={})
