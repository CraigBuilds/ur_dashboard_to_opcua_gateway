"""Verify the reusable RTDE client without requiring a robot."""

import types
import typing
import unittest.mock

import pytest
import universal_robots_clients.rtde_client as rtde_client


def _client() -> typing.Tuple[rtde_client.Client, unittest.mock.MagicMock, unittest.mock.MagicMock]:
    """Create one client backed by inspectable fake ur-rtde interfaces."""
    receiver = unittest.mock.MagicMock()
    writer = unittest.mock.MagicMock()

    return rtde_client.Client(receiver, writer, 42, 46), receiver, writer


def test_connect_configures_both_upper_range_interfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Create persistent receive and I/O interfaces with one shared configuration."""
    receiver = unittest.mock.MagicMock()
    writer = unittest.mock.MagicMock()
    receiver_constructor = unittest.mock.MagicMock(return_value=receiver)
    writer_constructor = unittest.mock.MagicMock(return_value=writer)
    receive_module = types.SimpleNamespace(RTDEReceiveInterface=receiver_constructor)
    io_module = types.SimpleNamespace(RTDEIOInterface=writer_constructor)
    monkeypatch.setattr(rtde_client, "_load_rtde_modules", lambda: (receive_module, io_module))

    client = rtde_client.connect("robot", frequency=20.0, use_upper_range_registers=True, verbose=True)

    assert isinstance(client, rtde_client.Client)
    assert (client._first_register, client._last_register) == (42, 46)
    receiver_constructor.assert_called_once_with("robot", 20.0, [], True, True)
    writer_constructor.assert_called_once_with("robot", True, True)


def test_failed_io_connection_closes_receive_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid leaking the first connection when the second connection fails."""
    receiver = unittest.mock.MagicMock()
    receive_module = types.SimpleNamespace(RTDEReceiveInterface=lambda *arguments: receiver)
    io_module = types.SimpleNamespace(RTDEIOInterface=unittest.mock.MagicMock(side_effect=ConnectionError("unavailable")))
    monkeypatch.setattr(rtde_client, "_load_rtde_modules", lambda: (receive_module, io_module))

    with pytest.raises(ConnectionError, match="unavailable"):
        rtde_client.connect("robot")

    receiver.disconnect.assert_called_once_with()


def test_typed_register_functions_delegate_and_report_failed_writes() -> None:
    """Delegate typed register access and turn false write results into errors."""
    client, receiver, writer = _client()
    receiver.getOutputIntRegister.return_value = 17
    receiver.getOutputDoubleRegister.return_value = 2.5
    writer.setInputIntRegister.return_value = True
    writer.setInputDoubleRegister.return_value = False

    assert rtde_client.read_output_int_register(client, 42) == 17
    assert rtde_client.read_output_double_register(client, 43) == 2.5
    rtde_client.write_input_int_register(client, 44, 21)

    with pytest.raises(RuntimeError, match="register 45"):
        rtde_client.write_input_double_register(client, 45, 3.5)

    receiver.getOutputIntRegister.assert_called_once_with(42)
    receiver.getOutputDoubleRegister.assert_called_once_with(43)
    writer.setInputIntRegister.assert_called_once_with(44, 21)
    writer.setInputDoubleRegister.assert_called_once_with(45, 3.5)


@pytest.mark.parametrize("register", [True, 41, 47, "42"])
def test_registers_are_validated(register: object) -> None:
    """Reject values outside the ur-rtde recipe before calling the native client."""
    client, receiver, writer = _client()

    with pytest.raises(ValueError, match="42 through 46"):
        rtde_client.read_output_int_register(client, typing.cast(int, register))

    receiver.getOutputIntRegister.assert_not_called()
    writer.assert_not_called()


def test_connection_health_reconnect_and_disconnect_cover_both_interfaces() -> None:
    """Coordinate lifecycle operations across both persistent interfaces."""
    client, receiver, writer = _client()
    receiver.isConnected.side_effect = [True, False]
    writer.isConnected.return_value = True
    receiver.reconnect.return_value = True

    assert rtde_client.is_connected(client) is True
    rtde_client.reconnect(client)
    rtde_client.disconnect(client)

    receiver.reconnect.assert_called_once_with()
    writer.reconnect.assert_not_called()
    writer.disconnect.assert_called_once_with()
    receiver.disconnect.assert_called_once_with()


def test_failed_reconnect_is_reported() -> None:
    """Raise a transport error when ur-rtde cannot restore a connection."""
    client, receiver, writer = _client()
    receiver.isConnected.return_value = True
    writer.isConnected.return_value = False
    writer.reconnect.return_value = False

    with pytest.raises(ConnectionError, match="I/O"):
        rtde_client.reconnect(client)
