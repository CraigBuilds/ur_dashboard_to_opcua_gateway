"""Verify the reusable Dashboard client in isolation."""

import typing
import unittest.mock

import pytest
import universal_robots_clients.dashboard_client as dashboard_client


@pytest.mark.parametrize("command", ["play\nstop", "play\rstop"])
def test_dashboard_rejects_line_breaks(command: str) -> None:
    """Reject protocol-line injection before opening a connection."""
    with pytest.raises(ValueError, match="line breaks"):
        dashboard_client.send_command("robot", command)


def test_dashboard_send_command_exchanges_one_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read a greeting, send one command, and return a stripped response."""
    stream = unittest.mock.MagicMock()
    stream.readline.side_effect = [b"Connected: Universal Robots Dashboard Server\n", b"Starting program\r\n"]
    connection = unittest.mock.MagicMock()
    connection.makefile.return_value = stream
    create_connection = unittest.mock.MagicMock(return_value=connection)
    monkeypatch.setattr(dashboard_client.socket, "create_connection", create_connection)

    assert dashboard_client.send_command("robot", "play", port=30000, timeout=2.5) == "Starting program"
    create_connection.assert_called_once_with(("robot", 30000), 2.5)
    stream.write.assert_called_once_with(b"play\n")


def test_named_dashboard_operations_format_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build exact Dashboard protocol strings while preserving endpoint values."""
    calls: typing.List[typing.Tuple[str, str, int, float]] = []

    def send_command(host: str, command: str, port: int = 29999, timeout: float = 5.0) -> str:
        """Capture one named Dashboard operation."""
        calls.append((host, command, port, timeout))

        return command

    monkeypatch.setattr(dashboard_client, "send_command", send_command)

    assert dashboard_client.load_program("robot", "Main.urp", 30000, 2.5) == "load Main.urp"
    assert dashboard_client.play_program("robot", 30000, 2.5) == "play"
    assert dashboard_client.load_and_play_program("robot", "Production/Pick.urp", 30000, 2.5) == "play"
    assert dashboard_client.pause_program("robot", 30000, 2.5) == "pause"
    assert dashboard_client.stop_program("robot", 30000, 2.5) == "stop"
    assert dashboard_client.get_program_state("robot", 30000, 2.5) == "programState"
    assert calls == [
        ("robot", "load Main.urp", 30000, 2.5),
        ("robot", "play", 30000, 2.5),
        ("robot", "load Production/Pick.urp", 30000, 2.5),
        ("robot", "play", 30000, 2.5),
        ("robot", "pause", 30000, 2.5),
        ("robot", "stop", 30000, 2.5),
        ("robot", "programState", 30000, 2.5),
    ]
