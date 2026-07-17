"""Test gateway protocol, validation, command, and lifecycle behaviour in isolation.

These tests complement ``test_components`` by exercising important failure branches and
adapter boundaries with deterministic fakes. They do not require Docker, a robot,
an SSH server, an OPC UA client, or any external network connection.
"""

import pathlib
import signal
import stat
import sys
import types
import typing
import unittest.mock

import asyncua.ua
import pytest
import ur_dashboard_to_opcua_gateway._01_main as main_module
import ur_dashboard_to_opcua_gateway._02_parse_command_line_args as parse_command_line_args
import ur_dashboard_to_opcua_gateway._04_discover_ur_programs as discover_ur_programs
import ur_dashboard_to_opcua_gateway._05_control_ur_programs_via_dashboard as control_ur_programs_via_dashboard
import ur_dashboard_to_opcua_gateway._06_combine_program_discovery_and_control as combine_program_discovery_and_control
import ur_dashboard_to_opcua_gateway._07_expose_program_commands_via_opcua as expose_program_commands_via_opcua

import tests.support.program_fixture as program_fixture
import tests.system.run as run_system_tests


def test_sftp_args_require_robot_host(capsys: pytest.CaptureFixture[str]) -> None:
    """Reject incomplete SFTP configuration before asking for credentials."""
    with pytest.raises(SystemExit) as error:
        parse_command_line_args.parse_args(["--catalog", "sftp"])

    assert error.value.code == 2
    assert "--robot-host is required for an SFTP catalogue." in capsys.readouterr().err


def test_sftp_args_prompt_for_password_and_preserve_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve prompted credentials and every configurable endpoint override."""
    monkeypatch.delenv("UR_ROBOT_PASSWORD", raising=False)
    prompts: typing.List[str] = []
    monkeypatch.setattr(parse_command_line_args.getpass, "getpass", lambda prompt: prompts.append(prompt) or "prompted-secret")

    args = parse_command_line_args.parse_args(
        [
            "--catalog",
            "sftp",
            "--programs-folder",
            "/robot/programs",
            "--robot-host",
            "robot.example",
            "--sftp-port",
            "2222",
            "--sftp-username",
            "operator",
            "--dashboard-host",
            "dashboard.example",
            "--dashboard-port",
            "30000",
            "--opcua-endpoint",
            "opc.tcp://127.0.0.1:5000/gateway/",
        ]
    )

    assert prompts == ["Robot password: "]
    assert args == parse_command_line_args.Args(
        catalog="sftp",
        programs_folder="/robot/programs",
        robot_host="robot.example",
        robot_password="prompted-secret",
        sftp_port=2222,
        sftp_username="operator",
        dashboard_host="dashboard.example",
        dashboard_port=30000,
        opcua_endpoint="opc.tcp://127.0.0.1:5000/gateway/",
    )


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (parse_command_line_args.Args(catalog="invalid"), "Unsupported catalogue"),
        (parse_command_line_args.Args(catalog="sftp", robot_password="secret"), "Robot host is required"),
        (parse_command_line_args.Args(catalog="sftp", robot_host="robot"), "Robot password is required"),
    ],
)
def test_discovery_rejects_invalid_configuration(args: parse_command_line_args.Args, message: str) -> None:
    """Report unsupported or incomplete discovery configuration clearly."""
    with pytest.raises(ValueError, match=message):
        discover_ur_programs.discover_programs(args)


def test_sftp_discovery_dispatches_resolved_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pass resolved SFTP configuration to the transport adapter."""
    captured: typing.Dict[str, object] = {}

    def discover(host: str, password: str, folder: pathlib.PurePosixPath, port: int, username: str) -> typing.List[str]:
        """Capture one SFTP discovery request."""
        captured.update(host=host, password=password, folder=folder, port=port, username=username)

        return ["Main.urp"]

    monkeypatch.setattr(discover_ur_programs, "_discover_sftp_programs", discover)
    args = parse_command_line_args.Args(
        catalog="sftp", programs_folder="/robot/programs", robot_host="robot", robot_password="secret", sftp_port=2222, sftp_username="operator"
    )

    assert discover_ur_programs.discover_programs(args) == ["Main.urp"]
    assert captured == {"host": "robot", "password": "secret", "folder": pathlib.PurePosixPath("/robot/programs"), "port": 2222, "username": "operator"}


def test_recursive_sftp_discovery_filters_and_relativizes_programs() -> None:
    """Walk nested SFTP folders and return only relative URP paths."""
    sftp = unittest.mock.MagicMock()
    entries = {
        "/programs": [
            types.SimpleNamespace(filename="Main.URP", st_mode=stat.S_IFREG),
            types.SimpleNamespace(filename="Production", st_mode=stat.S_IFDIR),
            types.SimpleNamespace(filename="notes.txt", st_mode=stat.S_IFREG),
        ],
        "/programs/Production": [
            types.SimpleNamespace(filename="PickPart.urp", st_mode=stat.S_IFREG),
            types.SimpleNamespace(filename="readme.md", st_mode=None),
        ],
    }
    sftp.listdir_attr.side_effect = lambda folder: entries[folder]
    root = pathlib.PurePosixPath("/programs")

    programs = list(discover_ur_programs._recursive_find_sftp_programs(sftp, root, root))

    assert programs == ["Main.URP", "Production/PickPart.urp"]
    assert [call.args[0] for call in sftp.listdir_attr.call_args_list] == ["/programs", "/programs/Production"]


def test_sftp_transport_configures_ssh_and_sorts_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure SSH, close both contexts, and sort transport results."""
    ssh = unittest.mock.MagicMock()
    sftp = unittest.mock.MagicMock()
    ssh.open_sftp.return_value.__enter__.return_value = sftp
    policy = object()
    paramiko = types.SimpleNamespace(SSHClient=lambda: ssh, AutoAddPolicy=lambda: policy)
    monkeypatch.setitem(sys.modules, "paramiko", paramiko)
    monkeypatch.setattr(discover_ur_programs, "_recursive_find_sftp_programs", lambda actual, root, folder: iter(["Z.urp", "A.urp"]))
    folder = pathlib.PurePosixPath("/programs")

    programs = discover_ur_programs._discover_sftp_programs("robot", "secret", folder, 2222, "operator")

    assert programs == ["A.urp", "Z.urp"]
    ssh.set_missing_host_key_policy.assert_called_once_with(policy)
    ssh.connect.assert_called_once_with("robot", port=2222, username="operator", password="secret")
    ssh.__enter__.assert_called_once_with()
    ssh.__exit__.assert_called_once()
    ssh.open_sftp.return_value.__enter__.assert_called_once_with()
    ssh.open_sftp.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("command", ["play\nstop", "play\rstop"])
def test_dashboard_rejects_line_breaks(command: str) -> None:
    """Reject both newline forms before opening a Dashboard connection."""
    with pytest.raises(ValueError, match="line breaks"):
        control_ur_programs_via_dashboard.send_command("127.0.0.1", 29999, command)


def test_dashboard_send_command_exchanges_one_protocol_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read the greeting, send one line, and return a stripped response."""
    stream = unittest.mock.MagicMock()
    stream.readline.side_effect = [b"Connected: Universal Robots Dashboard Server\n", b"Starting program\r\n"]
    connection = unittest.mock.MagicMock()
    connection.makefile.return_value = stream
    create_connection = unittest.mock.MagicMock(return_value=connection)
    monkeypatch.setattr(control_ur_programs_via_dashboard.socket, "create_connection", create_connection)

    response = control_ur_programs_via_dashboard.send_command("robot", 29999, "play", timeout=2.5)

    assert response == "Starting program"
    create_connection.assert_called_once_with(("robot", 29999), 2.5)
    connection.makefile.assert_called_once_with("rwb")
    stream.write.assert_called_once_with(b"play\n")
    stream.flush.assert_called_once_with()
    connection.__enter__.assert_called_once_with()
    connection.__exit__.assert_called_once()
    stream.__enter__.assert_called_once_with()
    stream.__exit__.assert_called_once()


@pytest.mark.parametrize(("responses", "message"), [([b""], "No greeting received"), ([b"Connected\n", b""], "No response received")])
def test_dashboard_reports_incomplete_exchanges(monkeypatch: pytest.MonkeyPatch, responses: typing.List[bytes], message: str) -> None:
    """Raise a connection error when the Dashboard closes unexpectedly."""
    stream = unittest.mock.MagicMock()
    stream.readline.side_effect = responses
    connection = unittest.mock.MagicMock()
    connection.makefile.return_value = stream
    monkeypatch.setattr(control_ur_programs_via_dashboard.socket, "create_connection", lambda address, timeout: connection)

    with pytest.raises(ConnectionError, match=message):
        control_ur_programs_via_dashboard.send_command("robot", 29999, "play")


def test_dashboard_commands_map_to_protocol_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind the configured endpoint and emit the exact Dashboard commands."""
    calls: typing.List[typing.Tuple[str, int, str, float]] = []

    def send_command(host: str, port: int, command: str, timeout: float = 5.0) -> str:
        """Capture one configured command."""
        calls.append((host, port, command, timeout))

        return command

    monkeypatch.setattr(control_ur_programs_via_dashboard, "send_command", send_command)
    args = parse_command_line_args.Args(catalog="local", dashboard_host="robot", dashboard_port=30000)
    commands = control_ur_programs_via_dashboard.create_dashboard_commands(args)

    assert commands["load"]("Production/PickPart.urp") == "load Production/PickPart.urp"
    assert commands["start"]() == "play"
    assert commands["pause"]() == "pause"
    assert commands["stop"]() == "stop"
    assert commands["status"]() == "programState"
    assert calls == [
        ("robot", 30000, "load Production/PickPart.urp", 5.0),
        ("robot", 30000, "play", 5.0),
        ("robot", 30000, "pause", 5.0),
        ("robot", 30000, "stop", 5.0),
        ("robot", 30000, "programState", 5.0),
    ]


def test_command_registry_preserves_supplied_functions() -> None:
    """Expose discovery and Dashboard functions under stable command names."""
    discover = lambda: ["Main.urp"]
    load = lambda program: program
    start = lambda: "started"
    dashboard_commands = {"load": load, "start": start}

    command_registry = combine_program_discovery_and_control.create_command_registry(discover, dashboard_commands)

    assert command_registry.commands == {"programs": discover, "load": load, "start": start}
    assert command_registry.commands["programs"] is discover
    assert command_registry.commands["load"] is load
    assert list(command_registry.program_operations) == ["Main.urp"]


def test_command_registry_binds_each_program_and_runs_in_order() -> None:
    """Create correctly bound load and run functions for every discovered program."""
    events: typing.List[str] = []

    def load(program: str) -> str:
        """Record a program load."""
        events.append(f"load:{program}")

        return f"loaded {program}"

    def start() -> str:
        """Record a program start."""
        events.append("start")

        return "started"

    discover = lambda: ["Main.urp", "Production/PickPart.urp"]
    dashboard_commands = {"load": load, "start": start}

    command_registry = combine_program_discovery_and_control.create_command_registry(discover, dashboard_commands)
    program_operations = command_registry.program_operations

    assert list(program_operations) == ["Main.urp", "Production/PickPart.urp"]
    assert program_operations["Main.urp"]["load"]() == "loaded Main.urp"
    assert events == ["load:Main.urp"]
    events.clear()
    assert program_operations["Production/PickPart.urp"]["run"]() == "loaded Production/PickPart.urp; started"
    assert events == ["load:Production/PickPart.urp", "start"]


def test_command_registry_requires_a_list_catalogue() -> None:
    """Reject a discovery command that violates the registry contract."""
    discover = lambda: "Main.urp"
    dashboard_commands = {"load": lambda program: program, "start": lambda: "started"}

    with pytest.raises(TypeError, match="must return a list"):
        combine_program_discovery_and_control.create_command_registry(discover, dashboard_commands)


def test_run_until_stopped_installs_handlers_and_closes_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the server context active until either installed signal requests shutdown."""
    server = unittest.mock.MagicMock()
    stopped = unittest.mock.MagicMock()
    handlers: typing.Dict[int, typing.Callable[[int, typing.Optional[types.FrameType]], None]] = {}

    def install_handler(number: int, handler: typing.Callable[[int, typing.Optional[types.FrameType]], None]) -> None:
        """Capture one process signal handler."""
        handlers[number] = handler

    def wait() -> None:
        """Simulate SIGTERM while the server context is active."""
        assert server.__enter__.called
        handlers[signal.SIGTERM](signal.SIGTERM, None)

    stopped.wait.side_effect = wait
    monkeypatch.setattr(main_module.threading, "Event", lambda: stopped)
    monkeypatch.setattr(main_module.signal, "signal", install_handler)

    main_module._run_until_stopped(server)

    assert set(handlers) == {signal.SIGINT, signal.SIGTERM}
    stopped.set.assert_called_once_with()
    server.__enter__.assert_called_once_with()
    server.__exit__.assert_called_once()


def test_opcua_method_metadata_reflects_command_signatures() -> None:
    """Generate scalar inputs and array outputs from command annotations."""
    parent = unittest.mock.MagicMock()

    def load(program: str) -> str:
        """Return one scalar result."""
        return program

    def programs() -> typing.List[str]:
        """Return one array result."""
        return ["Main.urp"]

    expose_program_commands_via_opcua._add_methods(parent, 4, {"load": load, "programs": programs})

    assert parent.add_method.call_count == 2
    load_call, programs_call = parent.add_method.call_args_list
    assert load_call.args[0:2] == (4, "load")
    assert [argument.Name for argument in load_call.args[3]] == ["program"]
    assert load_call.args[4][0].Name == "result"
    assert programs_call.args[0:2] == (4, "programs")
    assert programs_call.args[3] == []
    assert programs_call.args[4][0].ValueRank == asyncua.ua.ValueRank.OneDimension


def test_opcua_folder_cache_reuses_existing_path_nodes() -> None:
    """Create each nested folder once and reuse it for later program paths."""
    root = unittest.mock.MagicMock()
    production = unittest.mock.MagicMock()
    cell = unittest.mock.MagicMock()
    root.add_folder.return_value = production
    production.add_folder.return_value = cell
    folders: typing.Dict[pathlib.PurePosixPath, object] = {}
    path = pathlib.PurePosixPath("Production/Cell")

    first = expose_program_commands_via_opcua._get_program_folder(root, 4, path, folders)
    second = expose_program_commands_via_opcua._get_program_folder(root, 4, path, folders)

    assert first is cell
    assert second is cell
    root.add_folder.assert_called_once_with(4, "Production")
    production.add_folder.assert_called_once_with(4, "Cell")
    assert folders == {pathlib.PurePosixPath("Production"): production, path: cell}


def test_create_server_configures_endpoint_namespace_and_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build the server shell and pass application commands to both node adapters."""
    server = unittest.mock.MagicMock()
    server.register_namespace.return_value = 4
    robot = unittest.mock.MagicMock()
    server.nodes.objects.add_object.return_value = robot
    commands = {"programs": lambda: []}
    program_operations = {}
    command_registry = combine_program_discovery_and_control.CommandRegistry(commands=commands, program_operations=program_operations)
    method_calls: typing.List[typing.Tuple[object, int, object]] = []
    program_operation_calls: typing.List[typing.Tuple[object, int, object]] = []
    monkeypatch.setattr(expose_program_commands_via_opcua.asyncua.sync, "Server", lambda: server)
    monkeypatch.setattr(expose_program_commands_via_opcua, "_add_methods", lambda parent, namespace, actual: method_calls.append((parent, namespace, actual)))
    monkeypatch.setattr(
        expose_program_commands_via_opcua,
        "_add_program_operations",
        lambda parent, namespace, actual: program_operation_calls.append((parent, namespace, actual)),
    )

    result = expose_program_commands_via_opcua.create_server(command_registry, "opc.tcp://127.0.0.1:4840/gateway/")

    assert result is server
    server.set_endpoint.assert_called_once_with("opc.tcp://127.0.0.1:4840/gateway/")
    server.set_server_name.assert_called_once_with("ur_dashboard_to_opcua_gateway")
    server.set_security_policy.assert_called_once_with([asyncua.ua.SecurityPolicyType.NoSecurity])
    server.register_namespace.assert_called_once_with(expose_program_commands_via_opcua.OPC_NAMESPACE)
    server.nodes.objects.add_object.assert_called_once_with(4, "UR20")
    assert method_calls == [(robot, 4, commands)]
    assert program_operation_calls == [(robot, 4, program_operations)]


def test_program_fixture_archives_are_reproducible(tmp_path: pathlib.Path) -> None:
    """Produce identical URP bytes for the same logical program."""
    first = program_fixture.write_program(tmp_path / "first", "Main")
    second = program_fixture.write_program(tmp_path / "second", "Main")

    assert first.read_bytes() == second.read_bytes()


def test_configured_system_test_python_is_selected(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Use an explicitly configured supported interpreter."""
    configured = tmp_path / "python.exe"
    monkeypatch.setattr(run_system_tests, "_python_version", lambda command, repository: (3, 12, 4))

    command, version = run_system_tests._find_supported_python(tmp_path, configured)

    assert command == [str(configured.resolve())]
    assert version == (3, 12, 4)


@pytest.mark.parametrize(("version", "message"), [(None, "could not be run"), ((3, 8, 3), "Python 3.10 or later")])
def test_configured_system_test_python_is_validated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, version: typing.Optional[typing.Tuple[int, int, int]], message: str
) -> None:
    """Reject an unavailable or unsupported configured interpreter."""
    monkeypatch.setattr(run_system_tests, "_python_version", lambda command, repository: version)

    with pytest.raises(RuntimeError, match=message):
        run_system_tests._find_supported_python(tmp_path, tmp_path / "python.exe")


def test_system_test_command_forwards_selection_and_pytest_args(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """Build the expected collect-only pytest command and remove the forwarding separator."""
    captured: typing.List[typing.Tuple[typing.Sequence[str], pathlib.Path, typing.Optional[typing.Dict[str, str]]]] = []

    def run(command: typing.Sequence[str], cwd: pathlib.Path, environment: typing.Optional[typing.Dict[str, str]] = None) -> None:
        """Capture one runner command."""
        captured.append((command, cwd, environment))

    monkeypatch.setattr(run_system_tests, "_run", run)
    python = tmp_path / "python.exe"
    cache = tmp_path / "pytest-cache"

    run_system_tests._run_tests(python, tmp_path, cache, "sftp", True, ["--", "-q", "--maxfail=1"])

    assert cache.is_dir()
    assert len(captured) == 1
    command, cwd, environment = captured[0]
    assert command == [
        str(python),
        "-m",
        "pytest",
        "-c",
        "tests/pytest.ini",
        "-o",
        f"cache_dir={cache}",
        "-m",
        "system",
        "-k",
        "sftp",
        "--collect-only",
        "-q",
        "--maxfail=1",
    ]
    assert cwd == tmp_path
    assert environment is not None
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
