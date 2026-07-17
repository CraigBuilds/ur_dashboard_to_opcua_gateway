"""Verify the reusable Dashboard and program-discovery modules in isolation."""

import pathlib
import stat
import sys
import types
import typing
import unittest.mock

import pytest
import universal_robots_clients.dashboard as dashboard
import universal_robots_clients.program_discovery as program_discovery


def test_local_discovery_filters_relativizes_and_sorts(tmp_path: pathlib.Path) -> None:
    """Return only case-insensitive URP files as deterministic relative paths."""
    production = tmp_path / "Production"
    production.mkdir()
    (tmp_path / "Main.urp").touch()
    (production / "Pick.URP").touch()
    (tmp_path / "notes.txt").touch()

    assert program_discovery.discover_local_programs(tmp_path) == ["Main.urp", "Production/Pick.URP"]


def test_connected_sftp_discovery_recurses_without_owning_the_client() -> None:
    """Traverse a caller-owned SFTP client and normalize discovered paths."""
    sftp = unittest.mock.MagicMock()
    entries = {
        "/programs": [
            types.SimpleNamespace(filename="Main.URP", st_mode=stat.S_IFREG),
            types.SimpleNamespace(filename="Production", st_mode=stat.S_IFDIR),
            types.SimpleNamespace(filename="notes.txt", st_mode=stat.S_IFREG),
        ],
        "/programs/Production": [types.SimpleNamespace(filename="PickPart.urp", st_mode=stat.S_IFREG)],
    }
    sftp.listdir_attr.side_effect = lambda folder: entries[folder]

    assert program_discovery.discover_sftp_programs(sftp, "/programs") == ["Main.URP", "Production/PickPart.urp"]
    assert [call.args[0] for call in sftp.listdir_attr.call_args_list] == ["/programs", "/programs/Production"]


def test_sftp_convenience_function_makes_host_key_policy_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure, use, and close an optional Paramiko connection."""
    ssh = unittest.mock.MagicMock()
    sftp = unittest.mock.MagicMock()
    ssh.open_sftp.return_value.__enter__.return_value = sftp
    policy = object()
    paramiko = types.SimpleNamespace(SSHClient=lambda: ssh, AutoAddPolicy=lambda: policy)
    monkeypatch.setitem(sys.modules, "paramiko", paramiko)
    monkeypatch.setattr(program_discovery, "discover_sftp_programs", lambda actual, root: ["Main.urp"])

    programs = program_discovery.discover_programs_over_sftp(
        host="robot", root="/programs", username="operator", password="secret", port=2222, timeout=2.5, trust_unknown_host_keys=True
    )

    assert programs == ["Main.urp"]
    ssh.load_system_host_keys.assert_called_once_with()
    ssh.set_missing_host_key_policy.assert_called_once_with(policy)
    ssh.connect.assert_called_once_with("robot", port=2222, username="operator", password="secret", timeout=2.5)
    ssh.__enter__.assert_called_once_with()
    ssh.__exit__.assert_called_once()


@pytest.mark.parametrize("command", ["play\nstop", "play\rstop"])
def test_dashboard_rejects_line_breaks(command: str) -> None:
    """Reject protocol-line injection before opening a connection."""
    with pytest.raises(ValueError, match="line breaks"):
        dashboard.send_command("robot", command)


def test_dashboard_send_command_exchanges_one_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read a greeting, send one command, and return a stripped response."""
    stream = unittest.mock.MagicMock()
    stream.readline.side_effect = [b"Connected: Universal Robots Dashboard Server\n", b"Starting program\r\n"]
    connection = unittest.mock.MagicMock()
    connection.makefile.return_value = stream
    create_connection = unittest.mock.MagicMock(return_value=connection)
    monkeypatch.setattr(dashboard.socket, "create_connection", create_connection)

    assert dashboard.send_command("robot", "play", port=30000, timeout=2.5) == "Starting program"
    create_connection.assert_called_once_with(("robot", 30000), 2.5)
    stream.write.assert_called_once_with(b"play\n")


def test_named_dashboard_operations_format_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build exact Dashboard protocol strings while preserving endpoint values."""
    calls: typing.List[typing.Tuple[str, str, int, float]] = []

    def send_command(host: str, command: str, port: int = 29999, timeout: float = 5.0) -> str:
        """Capture one named Dashboard operation."""
        calls.append((host, command, port, timeout))

        return command

    monkeypatch.setattr(dashboard, "send_command", send_command)

    assert dashboard.load_program("robot", "Main.urp", 30000, 2.5) == "load Main.urp"
    assert dashboard.play_program("robot", 30000, 2.5) == "play"
    assert dashboard.pause_program("robot", 30000, 2.5) == "pause"
    assert dashboard.stop_program("robot", 30000, 2.5) == "stop"
    assert dashboard.get_program_state("robot", 30000, 2.5) == "programState"
    assert calls == [
        ("robot", "load Main.urp", 30000, 2.5),
        ("robot", "play", 30000, 2.5),
        ("robot", "pause", 30000, 2.5),
        ("robot", "stop", 30000, 2.5),
        ("robot", "programState", 30000, 2.5),
    ]
