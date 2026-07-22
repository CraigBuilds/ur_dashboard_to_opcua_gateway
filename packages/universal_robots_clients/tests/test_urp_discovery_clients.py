"""Verify the selector, local, and SFTP URP discovery clients."""

import pathlib
import stat
import sys
import types
import unittest.mock

import pytest
import universal_robots_clients.urp_discovery_client as urp_discovery_client
import universal_robots_clients.urp_discovery_local_client as urp_discovery_local_client
import universal_robots_clients.urp_discovery_sftp_client as urp_discovery_sftp_client


def test_local_discovery_filters_relativizes_and_sorts(tmp_path: pathlib.Path) -> None:
    """Return only case-insensitive URP files as deterministic relative paths."""
    production = tmp_path / "Production"
    production.mkdir()
    (tmp_path / "Main.urp").touch()
    (production / "Pick.URP").touch()
    (tmp_path / "notes.txt").touch()

    assert urp_discovery_local_client.discover_programs(tmp_path) == ["Main.urp", "Production/Pick.URP"]


def test_discovery_selector_delegates_to_local_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Select local discovery through the configuration-oriented client."""
    discover = unittest.mock.MagicMock(return_value=["Main.urp"])
    monkeypatch.setattr(urp_discovery_client.urp_discovery_local_client, "discover_programs", discover)

    assert urp_discovery_client.discover_programs("local", "/programs") == ["Main.urp"]
    discover.assert_called_once_with("/programs")


def test_discovery_selector_delegates_to_sftp_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forward all connection settings through the SFTP client selection."""
    discover = unittest.mock.MagicMock(return_value=["Main.urp"])
    monkeypatch.setattr(urp_discovery_client.urp_discovery_sftp_client, "connect_and_discover_programs", discover)

    programs = urp_discovery_client.discover_programs(
        "sftp", "/programs", host="robot", username="operator", password="secret", port=2222, timeout=2.5, trust_unknown_host_keys=True
    )

    assert programs == ["Main.urp"]
    discover.assert_called_once_with("robot", "/programs", "operator", "secret", 2222, 2.5, True)


def test_discovery_selector_rejects_unknown_backend() -> None:
    """Reject a backend name outside the package's supported choices."""
    with pytest.raises(ValueError, match="Unsupported URP-discovery backend"):
        urp_discovery_client.discover_programs("unknown", "/programs")


@pytest.mark.parametrize(("arguments", "message"), [({}, "host"), ({"host": "robot"}, "password")])
def test_discovery_selector_requires_sftp_connection_details(arguments: dict, message: str) -> None:
    """Reject incomplete SFTP configuration before loading the optional client."""
    with pytest.raises(ValueError, match=message):
        urp_discovery_client.discover_programs("sftp", "/programs", **arguments)


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

    assert urp_discovery_sftp_client.discover_programs(sftp, "/programs") == ["Main.URP", "Production/PickPart.urp"]
    assert [call.args[0] for call in sftp.listdir_attr.call_args_list] == ["/programs", "/programs/Production"]


def test_sftp_convenience_function_makes_host_key_policy_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure, use, and close an optional Paramiko connection."""
    ssh = unittest.mock.MagicMock()
    sftp = unittest.mock.MagicMock()
    ssh.open_sftp.return_value.__enter__.return_value = sftp
    policy = object()
    paramiko = types.SimpleNamespace(SSHClient=lambda: ssh, AutoAddPolicy=lambda: policy)
    monkeypatch.setitem(sys.modules, "paramiko", paramiko)
    monkeypatch.setattr(urp_discovery_sftp_client, "discover_programs", lambda actual, root: ["Main.urp"])

    programs = urp_discovery_sftp_client.connect_and_discover_programs(
        host="robot", root="/programs", username="operator", password="secret", port=2222, timeout=2.5, trust_unknown_host_keys=True
    )

    assert programs == ["Main.urp"]
    ssh.load_system_host_keys.assert_called_once_with()
    ssh.set_missing_host_key_policy.assert_called_once_with(policy)
    ssh.connect.assert_called_once_with("robot", port=2222, username="operator", password="secret", timeout=2.5)
    ssh.__enter__.assert_called_once_with()
    ssh.__exit__.assert_called_once()
